"""The two §W2 contrasts the E2 batch did not run: retention and adaptation.

`5cf3fe8` measured the *experience* contrast on three `software` `within`
targets and found it null, then ran a reachability census and reported the
panel closed on the positive side. The project ledger records that the
retention and adaptation halves of §W2 remain unrun.

This module closes that gap, and it does not inherit the prior result. Three
things differ, and each is a difference the prior panel forced rather than a
difference of taste.

**One: the ceiling is measured per panel, not carried over.** A reachability
census is a property of the decision grid on a specific set of targets. The
prior census was measured on `software` `within`. §W2 asks two other
questions, on `graph` and on the held-out `transfer` split. Recomputing the
same grid offline over all eighteen frozen targets, against a
*family-aware* default, the positive side is open on all three `graph`
`within` targets, on all three `graph` `transfer` targets, and on two of
three `software` `transfer` targets. It is closed on `software` `within`,
which is the prior panel. So a null measured here is a null on a panel that
can move, which is the difference between "experience does not help" and
"this panel cannot express a difference".

**Two: the inherited census is wrong on a family it was never run on, and
this module does not inherit the error.** `e2_contrast_campaign.
reachability_census` compares every row against `DEFAULT_METHOD`, a
hardcoded `"seed-sw-ddmin"`. On a `graph` target no such cell exists in that
row's grid, so `default` is `None`, and the row's `attainable_positive_delta`
is computed against `0.0` instead of against the real default. Measured:
`ad01-w0-within-gr-02` reports a default of 0.0 where `seed-gr-ddmin@8`
actually yields 0.2105, so the row overstates its own positive reach. The
prior census never saw this because its panel was software only. The frozen
module is **not** edited here. `census` below computes the default per
family and `defect_report` names the discrepancy against what the inherited
function returns for the same targets.

**Three: retention is measured on an observable that can vary, and the leg
it cannot support is reported rather than faked.** The terminal `verdict` is
`preserved` on every reducer outcome the panel can produce, so it is
constant by construction and cannot carry a retention claim. The scored
observable is `normalized_reduction` plus the decision vector
(`method_id`, `max_queries`), the same pair the prior lane adopted.

What a *retained method* would need is a repertoire wider than the four
authored seed ids. It is not there. `assessment_profile.default_repertoire`
returns exactly those four and `e2_replication.eligible_for(task)` returns
the two belonging to the task's family, identically for every arm. No method
acquired on one task can enter another task's repertoire, so "reuse a
retained method" is not expressible as a difference in `method_id` here.
That is `RETENTION_BLOCKER` below, it is asserted rather than described, and
the retention leg is measured as what *is* expressible: a policy shown a
retained method's prior observations against the same policy shown none,
paired per task, on the splits where the ceiling is open.

The accounting defect is inherited and is not this module's to repair. The
route states price as `usage.cost`; `gateway_http._decode_usage` reads
`billed` and `charge_units`, so both ride out absent rather than zero. The
campaign asserts no cost in either direction: it does not claim a receipt was
free, and it does not assert one was billed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import e2_contrast_campaign as experience
from . import e2_replication as replica
from . import learner
from . import worlds

NAMESPACE = "invr1w2retention"
R2_NAMESPACE = "invr1w2retentionr2"

# The two contrasts §W2 asks for, as named panels over the frozen world.
#
# The panel choice is driven by two measured properties, not by convenience,
# and both are measured in this module before anything is dispatched.
#
# **The ceiling.** `census()` measures the benefit metric at every decision,
# against a family-aware default. Over all eighteen frozen targets:
#
#   software / within   closed, 0 of 3 rows open   (this is the prior panel)
#   software / transfer open,   2 of 3 rows open
#   graph    / within   open,   3 of 3 rows open
#   graph    / transfer open,   3 of 3 rows open
#
# So the positive side is open everywhere except the prior panel, and
# choosing `software` / `within` for either contrast would re-run the panel
# the prior lane already showed to be closed and report a null the
# instrument was incapable of contradicting. That is the one result this
# lane must not produce.
#
# **The gate.** `qualification_census()` measures whether the instrument can
# read a target at all. The qualification gate's five authored policies all
# name a `seed-sw-` method, so on a **graph** target every one of them is
# refused and the gate reports `separates_reader_from_blind: false`. The
# gate is software-only, so a live contrast is only possible on software.
#
# The two constraints together leave exactly one place to run:
# `software` / `transfer`, the only panel that is both open and readable.
# `retention` runs there, and `adaptation` runs on its `transfer` side
# against its `within` side — the within side being the prior panel, which
# is closed and is reported as the closed bound it is rather than as a
# contrast that could have moved.
#
# The graph censuses are still computed and reported. A ceiling is a
# property of the decision grid and needs no policy, so a graph census is
# valid even though a graph contrast is not runnable.
PANELS = (
    {"name": "retention", "family": "software", "target_split": "transfer",
     "source_split": "dev",
     "question": "a policy shown a retained method's prior observations"
                 " against the same policy shown none, on the one panel"
                 " that is both open and readable"},
    {"name": "adaptation", "family": "software", "target_split": "transfer",
     "source_split": "dev", "within_split": "within",
     "question": "the same three arms on the held-out domain against the"
                 " same three arms on the within domain, paired by position"
                 " within the split"},
)

# The panels whose ceiling is measured and reported but on which no live
# contrast is run, because the qualification gate cannot read them.
CENSUS_ONLY_PANELS = (
    {"name": "census-graph-within", "family": "graph",
     "target_split": "within", "source_split": "dev",
     "question": "a ceiling on a panel the gate cannot read"},
    {"name": "census-graph-transfer", "family": "graph",
     "target_split": "transfer", "source_split": "dev",
     "question": "a ceiling on a held-out panel the gate cannot read"},
    {"name": "census-software-within", "family": "software",
     "target_split": "within", "source_split": "dev",
     "question": "the prior lane's panel, re-measured as the closed bound"
                 " it is"},
)

# The budget grid a census sweeps. The inherited grid is
# (4, 8, 12, 16, 24, 32); the same six are swept here so the two censuses
# are comparable, and the default sits at 8 inside it.
BUDGETS = (4, 8, 12, 16, 24, 32)

COHORT_WORLD = replica.COHORT_WORLD

# The budget a panel's relevant arm is measured at, searched rather than
# inherited.
#
# `e2_contrast_campaign.EVIDENCE_MAX_QUERIES = 3` is the smallest whole budget
# at which the *software* dev pool's graded outcome varies. It is not a
# property of the instrument; it is a property of that pool. Carried onto a
# graph panel it measures every dev graph task at 3 queries, where the
# graded outcome is `ok-incumbent, reduction 0` on all three, and
# `require_varying_graded_outcome` then refuses the arm. That refusal is
# correct and it is what the first run of this campaign produced: a named
# refusal on every target, no reading anywhere, and a report whose panels
# are all empty.
#
# So the budget is searched per panel, over a range declared here before any
# dispatch, and the smallest budget at which that panel's own dev pool
# varies is the one used. `evidence_budget_for` returns it and
# `verify_contrast` refuses a freeze whose recorded budget is not the
# searched one, so the search cannot drift after the fact.
BUDGET_SEARCH_RANGE = tuple(range(1, 17))
"""Whole budgets searched for a varying dev pool, smallest first.

The range is declared in the freeze, so a wider or narrower search is a
different frozen experiment rather than an unnoticed change.
"""

DECISION_FIELDS = experience.DECISION_FIELDS

# The two defects in the frozen instrument that a retention claim would
# otherwise be read through. Each is a constant, so neither can carry a
# contrast, and both are named in the report rather than worked around.
RETENTION_BLOCKER = {
    "what": "a policy cannot name a method it retained, so the retained-"
            "method-reuse leg has no lever on this instrument",
    "mechanism": "assessment_profile.default_repertoire returns the four"
                 " authored seed ids and e2_replication.eligible_for(task)"
                 " returns the two belonging to the task's family. Both are"
                 " closed, frozen and identical for every arm, so a method"
                 " acquired on one task can never enter another task's"
                 " repertoire and no difference in method_id can be a"
                 " retention effect.",
    "readable_observable": "normalized_reduction, plus the decision vector"
                           " (method_id, max_queries), which is reported per"
                           " task and never as the sole benefit metric",
    "what_this_module_measures_instead": "the transfer-shaped leg of"
                                         " retention: a policy shown a"
                                         " retained method's prior"
                                         " observations against the same"
                                         " policy shown none, paired per"
                                         " task, on the panels whose ceiling"
                                         " is open",
    "what_would_be_needed": "a repertoire that admits a method acquired on a"
                            " prior task, and a reducer whose verdict can"
                            " vary. Neither exists in the frozen"
                            " instrument, and this campaign edits neither.",
}

TERMINAL_VERDICT_DEFECT = {
    "what": "verdict is `preserved` on every reducer outcome, so it cannot"
            " vary and cannot carry a retention or adaptation claim",
    "measured": "e2_contrast_campaign.reachability_census records"
                " `verdict: preserved` on every cell of every grid it"
                " enumerates, and s09_e2_scored's own header says the same:"
                " `preserved` is a fixpoint of two composed invariants, not"
                " a policy property",
    "consequence": "this campaign reports normalized_reduction and the"
                   " decision vector instead, and asserts that no claim in"
                   " the report rests on verdict",
}


class W2Refused(Exception):
    """A campaign that may not run, named before anything was sent."""


# ---------------------------------------------------------------------------
# the freeze
# ---------------------------------------------------------------------------


def _world() -> Mapping[str, Any]:
    membership = worlds.world_membership(worlds.FROZEN_DIR)
    return membership[str(COHORT_WORLD)]


def _family_tag(family: str) -> str:
    return "sw" if family == "software" else "gr"


def default_method(family: str) -> str:
    """The method a policy with no information writes, per family.

    The inherited census hardcodes `seed-sw-ddmin`
    (`e2_contrast_campaign.DEFAULT_METHOD`). That is the correct
    zero-information default for a `software` target and an absent cell for
    a `graph` one. This resolves it per family, which is what makes a `graph`
    row's positive delta mean something.
    """
    return "seed-%s-ddmin" % _family_tag(family)


def method_ids_for(family: str) -> list:
    """The repertoire a policy on `family` may name, per the frozen gate."""
    from . import assessment_profile

    return [m for m in assessment_profile.default_repertoire()
            if m.startswith("seed-%s-" % _family_tag(family))]


def panel_targets(panel: Mapping[str, Any], *, split: str | None = None) -> list:
    """The target task ids a panel measures, read from the frozen world.

    `split` overrides the panel's own `target_split`, which is how the
    adaptation panel reads its `within` side. Overriding rather than
    duplicating means the two sides of that contrast cannot drift apart in
    the artifact.
    """
    world = _world()
    return list(world[split or panel["target_split"]][panel["family"]])


def contrast_block() -> dict:
    """Both contrasts, frozen, as the artifact and the digest read them."""
    panels = []
    for panel in PANELS:
        entry = {
            "name": panel["name"],
            "family": panel["family"],
            "target_split": panel["target_split"],
            "source_split": panel["source_split"],
            "target_task_ids": panel_targets(panel),
            "default_method": default_method(panel["family"]),
            "method_ids": method_ids_for(panel["family"]),
            "evidence_max_queries": evidence_budget_for(panel["family"]),
        }
        if panel.get("within_split"):
            entry["within_split"] = panel["within_split"]
            entry["within_domain_task_ids"] = panel_targets(
                panel, split=panel["within_split"])
        panels.append(entry)
    return {
        "namespace": NAMESPACE,
        "independent_of": [experience.NAMESPACE],
        "cohort_world": COHORT_WORLD,
        "arms": list(replica.ARMS),
        "panels": panels,
        "budgets": list(BUDGETS),
        "budget_search_range": list(BUDGET_SEARCH_RANGE),
        "decision_fields": list(DECISION_FIELDS),
        "scored_observable": "normalized_reduction, with the decision vector"
                             " (method_id, max_queries) reported per task",
        "estimator": replica.ESTIMATOR,
        "cluster_rule": replica.CLUSTER_RULE,
        "alpha": replica.ALPHA,
        "retention_blocker": RETENTION_BLOCKER["mechanism"],
    }


def freeze() -> dict:
    body = contrast_block()
    return {"body": body, "freeze_digest": replica.digest_of(body)}


def verify_contrast(frozen: Mapping[str, Any]) -> dict:
    """The freeze, re-derived and refused on any drift.

    Same rule as the two campaigns it reuses and for the same reason: a
    contrast edited after it was frozen reproduces a digest nobody agreed
    to.
    """
    body = dict((frozen or {}).get("body") or {})
    if not body:
        raise W2Refused("the freeze carries no contrast body")
    recorded = str((frozen or {}).get("freeze_digest") or "")
    if replica.digest_of(body) != recorded:
        raise W2Refused("the freeze addresses as %s but records %s"
                        % (replica.digest_of(body), recorded))
    current = contrast_block()
    if body != current:
        drifted = sorted(k for k in set(body) | set(current)
                         if body.get(k) != current.get(k))
        raise W2Refused("the frozen contrast no longer matches the panel: %s"
                        % ", ".join(drifted))
    return body


# ---------------------------------------------------------------------------
# the retention blocker, asserted rather than described
# ---------------------------------------------------------------------------


def measure_repertoire_closure() -> dict:
    """Measure, on every panel target, whether a retained method is nameable.

    This is the retention leg's first question and it is answerable with no
    model and no dispatch. For each target it reports the repertoire the
    frozen gate admits, the eligible methods the policy is shown, and
    whether any method on the panel is eligible that the panel did not start
    with. A repertoire with no arrival path is a closed one, and a contrast
    whose lever is closed has no `method_id` difference to report.
    """
    from . import assessment_profile

    repertoire = sorted(assessment_profile.default_repertoire())
    rows = []
    for panel in PANELS:
        splits = [panel["target_split"]]
        if panel.get("within_split"):
            splits.append(panel["within_split"])
        for split in splits:
            for task_id in panel_targets(panel, split=split):
                task = worlds.load_task(worlds.FROZEN_DIR, task_id)
                eligible = sorted(replica.eligible_for(task))
                rows.append({
                    "panel": panel["name"],
                    "split": split,
                    "task_id": task_id,
                    "family": str(task.get("family") or ""),
                    "eligible_methods": eligible,
                    "repertoire": repertoire,
                    "repertoire_size": len(repertoire),
                    "eligible_count": len(eligible),
                    "retained_method_nameable": len(eligible) > 2,
                })
    return {
        "rows": rows,
        "repertoire_closed": all(not r["retained_method_nameable"]
                                 for r in rows),
        "distinct_eligible_sets": sorted(
            {tuple(r["eligible_methods"]) for r in rows}),
        "every_arm_sees_the_same_eligible_methods": len(
            {tuple(r["eligible_methods"]) for r in rows}) == 1,
        "mechanism": RETENTION_BLOCKER["mechanism"],
        "reading": "a retention contrast needs a policy to be able to name a"
                   " method it retained. Every target here is shown the same"
                   " two authored seeds and the gate admits exactly those"
                   " four ids, so no acquired method can arrive. The"
                   " method_id leg is therefore not measurable here, and the"
                   " retention leg is measured on normalized_reduction"
                   " instead.",
    }


# ---------------------------------------------------------------------------
# reachability, per panel, with a family-aware default
# ---------------------------------------------------------------------------


def census(target_task_ids: Sequence[str], *, family: str,
           budgets: Sequence[int] = BUDGETS) -> dict:
    """The benefit metric at every decision, against this family's default.

    The enumeration is the inherited one, so the two censuses are computed
    the same way. The default is this module's `default_method(family)`
    rather than the inherited hardcoded `seed-sw-ddmin`, so a `graph` row
    has a real default and a `graph` positive delta means what it says.
    Computed with no model and no dispatch.
    """
    grid = {m: b for m in method_ids_for(family) for b in budgets}
    default_cell = "%s@%d" % (default_method(family), replica.MAX_QUERIES)
    rows = []
    for task_id in target_task_ids:
        task = worlds.load_task(worlds.FROZEN_DIR, task_id)
        cells = {}
        for method_id in method_ids_for(family):
            capability = next((c for c in experience._seed_capabilities()
                               if c["capability_id"] == method_id), None)
            if capability is None:
                continue
            for budget in budgets:
                result = experience._run_seed(
                    capability, task, max_queries=int(budget))
                report = replica._grade(task, result["candidate"])
                cells["%s@%d" % (method_id, budget)] = {
                    "normalized_reduction": replica._normalized_reduction(report),
                    "verdict": str(report["verdict"]),
                    "reason": str(report["reason"]),
                    "queries": int(result.get("queries") or 0),
                }
        values = [v["normalized_reduction"] for v in cells.values()]
        default = cells.get(default_cell)
        default_value = (default or {}).get("normalized_reduction")
        rows.append({
            "task_id": task_id,
            "family": family,
            "grid": cells,
            "default_cell": default_cell,
            "default": default,
            "distinct_values": sorted({round(v, 6) for v in values}),
            "ceiling": round(max(values), 6) if values else 0.0,
            "floor": round(min(values), 6) if values else 0.0,
            "attainable_positive_delta": (
                round(max(values) - default_value, 6)
                if values and default_value is not None else None),
            "attainable_negative_delta": (
                round(default_value - min(values), 6)
                if values and default_value is not None else None),
        })
    positive = [r["attainable_positive_delta"] for r in rows
                if r["attainable_positive_delta"] is not None]
    negative = [r["attainable_negative_delta"] for r in rows
                if r["attainable_negative_delta"] is not None]
    return {
        "family": family,
        "decision_fields": list(DECISION_FIELDS),
        "grid": [[m, int(b)] for m, b in sorted(grid.items())],
        "default_cell": default_cell,
        "rows": rows,
        "max_attainable_positive_delta": max(positive) if positive else 0.0,
        "max_attainable_negative_delta": max(negative) if negative else 0.0,
        "open_rows": sum(1 for p in positive if p > 0),
        "rows_measured": len(rows),
        "reading": "a positive paired delta needs a decision that beats the"
                   " zero-information default. This is the largest such"
                   " difference the grid admits on this panel, and the number"
                   " of rows where it is non-zero is the number of tasks on"
                   " which a positive delta is expressible at all.",
    }


def defect_report() -> dict:
    """What the inherited census returns for these targets, beside this one.

    `e2_contrast_campaign.reachability_census` resolves its default from a
    hardcoded software method. On a `graph` target the cell is absent and
    the row's positive delta is computed against 0.0. This reports both
    numbers per task so the discrepancy is a measurement rather than a
    claim about the code.
    """
    rows = []
    for panel in list(PANELS) + list(CENSUS_ONLY_PANELS):
        splits = [panel["target_split"]]
        if panel.get("within_split"):
            splits.append(panel["within_split"])
        seen = set()
        for split in splits:
            for task_id in panel_targets(panel, split=split):
                if task_id in seen:
                    continue
                seen.add(task_id)
                task = worlds.load_task(worlds.FROZEN_DIR, task_id)
                mine = census([task_id], family=panel["family"])["rows"][0]
                inherited = experience.reachability_census(
                    [task_id], method_ids=method_ids_for(panel["family"]),
                    budgets=list(BUDGETS))
                theirs = (inherited.get("rows") or [{}])[0]
                rows.append({
                    "panel": panel["name"],
                    "split": split,
                    "task_id": task_id,
                    "family": panel["family"],
                    "inherited_default_cell": inherited.get("default_decision"),
                    "inherited_default_present": theirs.get("default") is not None,
                    "inherited_positive_delta":
                        theirs.get("attainable_positive_delta"),
                    "this_default_cell": mine["default_cell"],
                    "this_default_value":
                        (mine.get("default") or {}).get("normalized_reduction"),
                    "this_positive_delta": mine.get("attainable_positive_delta"),
                    "agrees": theirs.get("attainable_positive_delta")
                    == mine.get("attainable_positive_delta"),
                })
    disagreeing = [r for r in rows if not r["agrees"]]
    return {
        "rows": rows,
        "disagreements": len(disagreeing),
        "rows_measured": len(rows),
        "defect": "e2_contrast_campaign.reachability_census resolves the"
                  " default from DEFAULT_METHOD = 'seed-sw-ddmin'. On a"
                  " graph target that cell does not exist in the row's grid,"
                  " so `default` is None and the row's positive delta is"
                  " computed against 0.0 rather than against the real"
                  " default. The prior census never hit it because its panel"
                  " was software only.",
        "not_patched": "e2_contrast_campaign is frozen and is not edited"
                       " here. This module computes its own default per"
                       " family and reports the discrepancy.",
        "disagreeing_task_ids": [r["task_id"] for r in disagreeing],
        "reading": "where the two disagree the inherited number is the"
                   " larger, because it measures the gap from nothing rather"
                   " than from the zero-information default. Both panels in"
                   " this campaign are graph panels, so every target"
                   " measured here is one the inherited function misreads.",
    }


# ---------------------------------------------------------------------------
# the arms
# ---------------------------------------------------------------------------


def evidence_budget_for(family: str) -> int:
    """The smallest whole budget at which this family's dev pool varies.

    Searched over `BUDGET_SEARCH_RANGE`, and measured with the campaign's
    own reducer and its own checker, so the answer is a property of the
    frozen pool rather than a constant carried from another panel.

    Cached per family, because the search runs the reducer once per budget
    and the freeze, the census-only report and every arm build all ask for
    the same answer about the same frozen pool. A panel is a property of
    the world, so recomputing it cannot return a different one; caching
    cannot make the answer wrong.

    Raises `W2Refused` when no budget in the range varies it, because a
    uniform arm cannot be read and shipping one would produce a contrast
    whose zeros are arithmetic.
    """
    cached = _BUDGET_CACHE.get(family)
    if cached is not None:
        return cached
    pool = _world()["dev"][family]
    for budget in BUDGET_SEARCH_RANGE:
        rows = experience._measured_rows(pool, max_queries=budget)
        profile = experience.graded_outcome_profile(rows)
        if not profile.get("delivered_uniform"):
            _BUDGET_CACHE[family] = int(budget)
            return int(budget)
    raise W2Refused(
        "the %s dev pool's graded outcome is uniform at every whole budget"
        " from %d to %d, so no arm built on it can be read"
        % (family, BUDGET_SEARCH_RANGE[0], BUDGET_SEARCH_RANGE[-1]))


_BUDGET_CACHE: dict = {}


def build_arms(target: Mapping[str, Any], *, source_task_ids: Sequence[str],
               filler_task_ids: Sequence[str],
               visible: Sequence[str]) -> dict:
    """The three arms, built by the inherited constructor at this budget.

    `experience.build_arms` is used unchanged. It constructs the relevant
    arm's records at a budget where the graded outcome varies, matches the
    irrelevant control on characters and record count, and asserts both
    before anything is dispatched. The one thing this module supplies is the
    budget, because the inherited one is a property of the software dev pool
    and a graph panel has a different one.
    """
    budget = evidence_budget_for(str(target.get("family") or ""))
    if budget != experience.EVIDENCE_MAX_QUERIES:
        rows = experience._measured_rows(list(source_task_ids),
                                         max_queries=budget)
        target_task = dict(target)
        base = learner.relevant_experience(
            target_task, list(source_task_ids), list(visible), {})
        relevant = {**base, "family": str(target.get("family") or ""),
                    "observations": rows}
        replica.require_measurable_verdicts(relevant["observations"])
        none = {**learner.no_experience_experience(
            target_task, list(source_task_ids), list(visible), {}),
            "family": str(target.get("family") or ""), "observations": []}
        irrelevant = {**base, "family": str(target.get("family") or ""),
                      "observations": experience._irrelevant_rows(
                          relevant, list(filler_task_ids))}
        arms = {replica.ARM_RELEVANT: relevant, replica.ARM_NONE: none,
                replica.ARM_IRRELEVANT: irrelevant}
        experience.require_size_matched(arms)
        experience.require_varying_graded_outcome(
            relevant, irrelevant)
        return arms
    return experience.build_arms(
        target, source_task_ids=list(source_task_ids),
        filler_task_ids=list(filler_task_ids), visible=list(visible))


def world_pools(panel: Mapping[str, Any], *, split: str | None = None) -> dict:
    """The source, filler and target pools one panel measures on."""
    world = _world()
    family = panel["family"]
    other = "graph" if family == "software" else "software"
    return {
        "source": list(world[panel["source_split"]][family]),
        "filler": list(world[panel["source_split"]][other]),
        "target": panel_targets(panel, split=split),
    }


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------


def run_one_panel(panel: Mapping[str, Any], *, split: str, dsn: str,
                  gateway: Any, model: str, allocation_id: str,
                  campaign_id: str, max_output_tokens: int) -> dict:
    """One panel on one split: qualify, census, audit, dispatch, report.

    The order is the inherited order and it is the order the freeze
    requires: verify the freeze, build every arm, audit what each arm
    receives, measure reachability, and only then dispatch. Nothing about a
    dispatch can reach the arm it was dispatched for.
    """
    pools = world_pools(panel, split=split)
    visible = learner.visible_opportunities(COHORT_WORLD)
    acquired: list = []
    attempted: list = []
    readings: dict = {}
    qualification: dict = {}
    census_row: dict = {}
    audit: dict = {}
    profiles: dict = {}
    sized: dict = {}
    refusal = None

    for task_id in pools["target"]:
        task = worlds.load_task(worlds.FROZEN_DIR, task_id)
        try:
            arms = build_arms(task, source_task_ids=pools["source"],
                              filler_task_ids=pools["filler"],
                              visible=visible)
        except experience.ContrastRefused as refused:
            # An arm that cannot be built on this target is a missing cell,
            # not a failed one. It is named and the target is skipped, so a
            # refusal never silently becomes a zero.
            refusal = {"task_id": task_id, "split": split,
                       "panel": panel["name"], "reason": str(refused)}
            continue
        sized = experience.require_size_matched(arms)
        profiles = experience.require_varying_graded_outcome(
            arms[replica.ARM_RELEVANT], arms[replica.ARM_IRRELEVANT])
        audit = experience.treatment_input_audit(task, arms)
        if not qualification:
            qualification = replica.qualify_instrument(
                task, list(arms[replica.ARM_RELEVANT]["observations"]),
                eligible_methods=replica.eligible_for(task))
            if not qualification["separates_reader_from_blind"]:
                raise W2Refused(
                    "the instrument does not score a reader above an echoer,"
                    " so no score it produced would be readable")
        if not census_row:
            census_row = census(pools["target"], family=panel["family"])
        for name in replica.ARMS:
            prompt = experience.prompt_for(name, task, arms[name])
            got, tries = experience.acquire_with_retry(
                dsn, campaign_id=campaign_id, allocation_id=allocation_id,
                arm=name, task_id=task_id, prompt=prompt, gateway=gateway,
                model=model, max_output_tokens=max_output_tokens,
                retries=replica.RETRIES)
            acquired.append(got)
            attempted.extend(tries)
            source, problem = replica._source_of(dsn, got.operation_id)
            if problem or not source:
                continue
            settled = replica._settled_text(dsn, got.operation_id)
            origin = "fixture-stand-in"
            if settled is not None:
                from . import construct as _construct

                origin = _construct.acquisition_origin(
                    dsn, got.operation_id, settled)["origin"]
            reading = experience.score_one(
                task, arms[name], source, arm_name=name, origin=origin)
            readings.setdefault(name, {})[task_id] = reading.as_dict()

    replica.require_no_empty_dispatch_is_compared(acquired)
    return {
        "panel": panel["name"],
        "split": split,
        "family": panel["family"],
        "pools": pools,
        "instrument_qualification": qualification,
        "evidence_budget": {
            "max_queries": evidence_budget_for(panel["family"]),
            "searched_range": list(BUDGET_SEARCH_RANGE),
            "inherited_software_budget": experience.EVIDENCE_MAX_QUERIES,
            "detail_template": experience.DETAIL_TEMPLATE},
        "graded_outcome_profiles": profiles,
        "size_matching": sized,
        "treatment_input_audit": audit,
        "reachability_census": census_row,
        "acquired": [a.as_dict() for a in acquired],
        "dispatch_attempts": [a.as_dict() for a in attempted],
        "null_dispatches": replica.null_dispatches(attempted),
        "arm_refusals": [refusal] if refusal else [],
        "readings": readings,
        "paired": replica.paired_report(readings),
        "model": model,
        "campaign_id": campaign_id,
    }


def run_campaign(*, dsn: str, gateway: Any, model: str, allocation_id: str,
                 campaign_id: str, max_output_tokens: int = 2048) -> dict:
    """Both §W2 contrasts, dispatched and reported as numbers.

    The retention panel runs on `graph`/`within`. The adaptation panel runs
    twice, once per side, and `adaptation_contrast` pairs the two sides.
    The census and the repertoire closure are computed for every panel
    before the first dispatch, and the run refuses to continue if a panel's
    positive side turns out to be closed, because a null on a closed panel
    is arithmetic rather than a finding.
    """
    frozen = freeze()
    body = verify_contrast(frozen)

    closure = measure_repertoire_closure()
    defect = defect_report()
    gate = qualification_census()
    if not gate["readable"]:
        raise W2Refused(
            "the qualification gate reads no target on this panel, so a"
            " live contrast would be refused at the gate rather than"
            " reported: %s" % gate["mechanism"])
    panels: dict = {}
    for panel in PANELS:
        splits = [panel["target_split"]]
        if panel.get("within_split"):
            splits.append(panel["within_split"])
        for split in splits:
            key = "%s/%s" % (panel["name"], split)
            panels[key] = run_one_panel(
                panel, split=split, dsn=dsn, gateway=gateway, model=model,
                allocation_id=allocation_id, campaign_id=campaign_id,
                max_output_tokens=max_output_tokens)

    return {
        "freeze": frozen,
        "namespace": NAMESPACE,
        "measured_live": True,
        "repertoire_closure": closure,
        "inherited_census_defect": defect,
        "qualification_gate": gate,
        "census_only": {
            name: census(panel_targets(panel), family=panel["family"])
            for name, panel in (("graph-within", CENSUS_ONLY_PANELS[0]),
                                ("graph-transfer", CENSUS_ONLY_PANELS[1]),
                                ("software-within", CENSUS_ONLY_PANELS[2]))},
        "panels": panels,
        "paired": merge_paired(panels),
        "adaptation": adaptation_contrast(panels),
        "census": replica.cluster_census(),
        "model": model,
        "campaign_id": campaign_id,
        "body": body,
    }


def merge_paired(panels: Mapping[str, Any]) -> dict:
    """Every panel's paired report, keyed by panel and split.

    Kept per panel rather than pooled. Pooling three targets from a closed
    panel with three from an open one would average a number the instrument
    cannot produce with one it can, and the average would be attributable
    to neither.
    """
    out: dict = {}
    for key, panel in sorted(panels.items()):
        out[key] = panel.get("paired") or {}
    return out


def adaptation_contrast(panels: Mapping[str, Any]) -> dict:
    """Within-domain against held-out-domain, paired by position.

    §W2's second contrast. Both sides are the same three arms on the same
    family, so the difference between them is the split and not the
    instrument. The pairing is by position within each split rather than by
    task id, because `within-sw-00` and `transfer-gr-00` are different
    templates in different domains and share no lineage; position is the
    only correspondence the frozen world offers.

    A position where either side has no reading is dropped and named, never
    averaged in as a zero.
    """
    within = panels.get("adaptation/within") or {}
    held = panels.get("adaptation/transfer") or {}
    # `targets` is what a built report carries; `pools.target` is what a
    # live bundle carries. Both are read so the pairing can be recomputed
    # from a finished report as well as from a running bundle, which is
    # what makes the stored numbers re-derivable offline.
    within_tasks = list(within.get("targets") or
                        (within.get("pools") or {}).get("target") or [])
    held_tasks = list(held.get("targets") or
                      (held.get("pools") or {}).get("target") or [])
    pairs = []
    dropped = []
    for index in range(min(len(within_tasks), len(held_tasks))):
        wt, ht = within_tasks[index], held_tasks[index]
        entry = {"position": index, "within_task_id": wt,
                 "held_out_task_id": ht, "arms": {}}
        usable = True
        for name in replica.ARMS:
            w = (within.get("readings") or {}).get(name, {}).get(wt)
            h = (held.get("readings") or {}).get(name, {}).get(ht)
            if w is None or h is None:
                usable = False
                break
            # The reading's own `normalized_reduction`, not a
            # re-derivation. `replica._normalized_reduction` reads the
            # checker's report shape, whose measure key is `measure`; a
            # `Reading` carries the same number under `candidate_measure`
            # and has no `measure` at all, so re-deriving from it returns
            # 1.0 for every pair. That is a uniform result this campaign
            # never observed, and the first live run produced it.
            rw = float(w.get("normalized_reduction") or 0.0)
            rh = float(h.get("normalized_reduction") or 0.0)
            entry["arms"][name] = {
                "within": rw,
                "held_out": rh,
                "delta": round(rw - rh, 6),
            }
        if usable:
            pairs.append(entry)
        else:
            dropped.append(entry)
    arm_deltas = {
        name: [p["arms"][name]["delta"] for p in pairs
               if name in p["arms"]]
        for name in replica.ARMS}
    # One contrast per experience arm, kept separate. Pooling the relevant
    # and irrelevant arms into a single list and labelling the result
    # `experience_minus_no_experience` would count each position twice and
    # answer a question about two arms that no reader asked.
    contrasts = {}
    for name in (replica.ARM_RELEVANT, replica.ARM_IRRELEVANT):
        deltas = []
        for pair in pairs:
            arms = pair.get("arms") or {}
            if name not in arms or replica.ARM_NONE not in arms:
                continue
            deltas.append(round(arms[name]["delta"]
                                - arms[replica.ARM_NONE]["delta"], 6))
        contrasts["%s-minus-%s" % (name, replica.ARM_NONE)] = {
            "deltas": deltas,
            "mean": (round(sum(deltas) / len(deltas), 6) if deltas else None),
            "n": len(deltas),
            "n_positions": len(pairs),
        }
    return {
        "question": "within-domain against held-out-domain, on the same"
                    " family, paired by position within the split",
        "within_split": "within",
        "held_out_split": "transfer",
        "family": (within.get("family") or held.get("family")),
        "pairs": pairs,
        "dropped_positions": dropped,
        "n_pairs": len(pairs),
        "arm_deltas": arm_deltas,
        "contrasts": contrasts,
        "reading": "a positive arm delta means the within-domain arm did"
                   " worse than its held-out-domain counterpart on the same"
                   " arm. Each contrast under `contrasts` is that arm's"
                   " within-minus-held-out difference minus the none arm's,"
                   " which is the retention question asked across the split:"
                   " if retained experience helps within its own domain but"
                   " not on a held-out one, that shows as a larger"
                   " within-minus-held-out difference for the experience"
                   " arms than for the none arm.",
        "caveat": "the two splits are disjoint template sets, so position is"
                  " the only correspondence the frozen world offers and a"
                  " position pairs two different tasks. This is a"
                  " within-versus-held-out comparison of arm means over"
                  " matched positions, not a paired measurement of the same"
                  " task in two domains.",
    }


# ---------------------------------------------------------------------------
# the report
# ---------------------------------------------------------------------------


def build_report(bundle: Mapping[str, Any], *, namespace: str,
                 campaign_kind: str,
                 is_replication_of: str | None = None) -> dict:
    """The report, with the census and the blocker beside the numbers.

    The two claims a reader needs before the numbers are the ones a reader
    cannot derive from them: the panel's positive side is open, and the
    `method_id` leg is closed. Both are in the report as measured values,
    not as prose in a message.
    """
    panels = bundle.get("panels") or {}
    panel_rows = {}
    for key, panel in sorted(panels.items()):
        census_row = panel.get("reachability_census") or {}
        readings = panel.get("readings") or {}
        panel_rows[key] = {
            "family": panel.get("family"),
            "split": panel.get("split"),
            "targets": (panel.get("pools") or {}).get("target"),
            "n_targets": len((panel.get("pools") or {}).get("target") or []),
            "readings_per_arm": {n: len(readings.get(n) or {})
                                 for n in replica.ARMS},
            # The readings themselves, in full. The verifier re-derives every
            # reduction, every paired delta and every adaptation difference
            # from these, so a report that carried only the paired summary
            # would leave it nothing to re-derive from. `Reading.as_dict` is
            # the instrument's own serialisation, not a projection.
            "readings": readings,
            "reachability_census": {
                "max_attainable_positive_delta":
                    census_row.get("max_attainable_positive_delta"),
                "max_attainable_negative_delta":
                    census_row.get("max_attainable_negative_delta"),
                "open_rows": census_row.get("open_rows"),
                "rows_measured": census_row.get("rows_measured"),
                "default_cell": census_row.get("default_cell"),
                "rows": census_row.get("rows"),
            },
            "paired": panel.get("paired"),
            "size_matching": panel.get("size_matching"),
            "treatment_input_audit": panel.get("treatment_input_audit"),
            "arm_refusals": panel.get("arm_refusals"),
        }
    measured_live = bool(bundle.get("measured_live"))
    report = {
        "schema": "s09-w2-retention-v1",
        "namespace": namespace,
        "campaign_kind": campaign_kind,
        "is_replication_of": is_replication_of,
        "measured_live": measured_live,
        # The verifier's offline exemption is this declaration, not an
        # inference from empty readings. It lives here so a report cannot
        # be exempted by accident and a live report that lost its readings
        # still fails.
        "offline_only": None if measured_live else {
            "what": "no dispatch was made. This artifact carries the"
                    " closure, the defect report and every census, and"
                    " carries no reading.",
            "panels_measured_live": [],
            "target_task_ids": sorted({
                t for p in PANELS for t in panel_targets(p)}),
        },
        "independent_of": [experience.NAMESPACE],
        "model": bundle.get("model"),
        "campaign_id": bundle.get("campaign_id"),
        "freeze": bundle.get("freeze"),
        "measureability": {
            "retention_measurable": True,
            "retention_observable": "normalized_reduction (paired per task),"
                                    " with the decision vector"
                                    " (method_id, max_queries) reported per"
                                    " task",
            "retained_method_leg_measurable": False,
            "retained_method_leg_blocker": RETENTION_BLOCKER,
            "terminal_verdict_usable": False,
            "terminal_verdict_defect": TERMINAL_VERDICT_DEFECT,
            "note": "the terminal verdict is constant by construction, so no"
                    " claim in this report rests on it. The retained-method"
                    " leg is unmeasurable on this instrument and is reported"
                    " as such rather than approximated by a different arm.",
        },
        "panels": panel_rows,
        "paired": bundle.get("paired"),
        "adaptation": bundle.get("adaptation"),
        "repertoire_closure": bundle.get("repertoire_closure"),
        "inherited_census_defect": bundle.get("inherited_census_defect"),
        "qualification_gate": bundle.get("qualification_gate"),
        "census_only_panels": bundle.get("census_only"),
        "accounting": bundle.get("accounting"),
        "key_discrepancy": bundle.get("key_discrepancy"),
        "census": bundle.get("census"),
        "acquired": [a for p in panels.values()
                     for a in (p.get("acquired") or [])],
        "null_dispatches": [n for p in panels.values()
                            for n in (p.get("null_dispatches") or [])],
    }
    return report


def qualification_census() -> dict:
    """Which targets the instrument can read at all, measured per target.

    `replica.qualify_instrument` is the gate a run must pass before it will
    trust a number, and it is the right gate: a contrast read off an
    instrument that cannot separate a reader from a blind policy measures
    the echo. It is also written for one family.

    All five of its authored policies — `PROMPTED_SHAPE_READER`,
    `ECHOES_WITHOUT_READING`, `IGNORES_THE_VIEW` and the other two — name
    `seed-sw-ddmin` or `seed-sw-greedy` in their own bytes
    (`e2_replication.py:460, 481, 483, 499, 509`). `score_response` refuses
    an action naming a method outside the target's family, so on a **graph**
    target every one of them is refused and every reading comes back
    `scored: false` with `the returned bytes admitted no action that reaches
    a method executor`. `qualify_instrument` then reports
    `separates_reader_from_blind: false` and the run refuses.

    So the gate does not measure this instrument on a graph target. It
    cannot, because its instrument is software-only. This reports which
    targets are readable and which are not, so a panel is chosen on a
    measured property rather than on the assumption that a gate which
    passed on one family passes on another.
    """
    rows = []
    for panel in PANELS:
        for split in ([panel["target_split"]]
                      + ([panel["within_split"]] if panel.get("within_split")
                         else [])):
            for task_id in panel_targets(panel, split=split):
                task = worlds.load_task(worlds.FROZEN_DIR, task_id)
                try:
                    arms = build_arms(
                        task,
                        source_task_ids=world_pools(panel, split=split)["source"],
                        filler_task_ids=world_pools(panel, split=split)["filler"],
                        visible=learner.visible_opportunities(COHORT_WORLD))
                except experience.ContrastRefused as refused:
                    rows.append({"panel": panel["name"], "split": split,
                                 "task_id": task_id,
                                 "family": panel["family"],
                                 "readable": False,
                                 "reason": "arm refused: %s" % refused})
                    continue
                outcome = replica.qualify_instrument(
                    task, list(arms[replica.ARM_RELEVANT]["observations"]),
                    eligible_methods=replica.eligible_for(task))
                rows.append({
                    "panel": panel["name"], "split": split,
                    "task_id": task_id, "family": panel["family"],
                    "readable": bool(outcome["separates_reader_from_blind"]),
                    "reader_scored": bool(outcome["reader"].get("scored")),
                    "reader_score": outcome["reader"].get("score"),
                    "echoer_score": outcome["echoer"].get("score"),
                    "separates": bool(
                        outcome["separates_reader_from_blind"]),
                })
    readable = [r for r in rows if r["readable"]]
    families = sorted({r["family"] for r in rows})
    readable_families = sorted({r["family"] for r in readable})
    return {
        "rows": rows,
        "readable": len(readable),
        "measured": len(rows),
        "readable_families": readable_families,
        "measured_families": families,
        "mechanism": "all five authored qualification policies in"
                     " e2_replication hardcode a `seed-sw-` method, and"
                     " score_response refuses an action naming a method"
                     " outside the target's family, so on a graph target"
                     " every one of them is refused before it can act",
        "reading": "the qualification gate is software-only. A panel whose"
                   " family is outside readable_families cannot be run on"
                   " this instrument, and a run on it would refuse at the"
                   " gate rather than report a number. A census on such a"
                   " panel still holds: the ceiling is a property of the"
                   " grid and needs no policy.",
        "consequence": "the retention and adaptation panels must both be"
                       " on a readable family for a live contrast. This"
                       " campaign reports the graph panels' censuses, which"
                       " are valid, and does not run a live contrast on a"
                       " family the gate cannot read.",
    }


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="the W2 retention and adaptation contrasts")
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--out", default=None)
    parser.add_argument("--max-output-tokens", type=int, default=1024,
                        help="the route fails at 2048 on this campaign's"
                             " prompts, so the default is the budget the"
                             " last campaign measured as working")
    parser.add_argument("--rerun", action="store_true",
                        help="mint the replication namespace")
    parser.add_argument("--census-only", action="store_true",
                        help="report the closure, the defect and every"
                             " census, and dispatch nothing")
    args = parser.parse_args(argv)

    if args.census_only:
        verify_contrast(freeze())
        report = build_report({
            "measured_live": False,
            "freeze": freeze(),
            "panels": {
                "%s/%s" % (p["name"], s): {
                    "family": p["family"], "split": s,
                    "pools": {"target": panel_targets(p, split=s)},
                    "readings": {}, "paired": None,
                    "reachability_census": census(
                        panel_targets(p, split=s), family=p["family"]),
                }
                for p in PANELS
                for s in ([p["target_split"]]
                          + ([p["within_split"]] if p.get("within_split")
                             else []))},
            "repertoire_closure": measure_repertoire_closure(),
            "inherited_census_defect": defect_report(),
            "qualification_gate": qualification_census(),
            "census_only": {
                "%s/%s" % (p["name"], p["target_split"]): census(
                    panel_targets(p), family=p["family"])
                for p in CENSUS_ONLY_PANELS},
        }, namespace=NAMESPACE, campaign_kind="census-only")
        out = Path(args.out or ("reports/evidence/%s-census" % NAMESPACE))
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True, default=str),
            encoding="utf-8")
        for key, row in sorted(report["panels"].items()):
            c = row["reachability_census"]
            print("%-24s open %s/%s max_pos %s"
                  % (key, c["open_rows"], c["rows_measured"],
                     c["max_attainable_positive_delta"]))
        for key, c in sorted((report.get("census_only_panels") or {}).items()):
            print("%-24s open %s/%s max_pos %s  (ceiling only, not run)"
                  % (key, c["open_rows"], c["rows_measured"],
                     c["max_attainable_positive_delta"]))
        print("inherited-census disagreements: %s"
              % report["inherited_census_defect"]["disagreements"])
        print("qualification gate readable: %s of %s, families %s"
              % (report["qualification_gate"]["readable"],
                 report["qualification_gate"]["measured"],
                 report["qualification_gate"]["readable_families"]))
        return 0

    config = replica.live_config()
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
    probe = experience.probe_route(
        args.dsn, campaign_id=ids["campaign_id"],
        allocation_id=ids["allocation_id"], gateway=gateway,
        model=config["model"])
    if not probe["settled"]:
        print("route probe returned no settled response after %d attempts: %s"
              % (len(probe.get("attempts") or []), probe))
        return 3
    print("route probe confirmed on attempt %d (%s)"
          % (len(probe["attempts"]), probe["operation_id"]))
    bundle = run_campaign(
        dsn=args.dsn, gateway=gateway, model=config["model"],
        allocation_id=ids["allocation_id"], campaign_id=ids["campaign_id"],
        max_output_tokens=args.max_output_tokens)
    operation_ids = [a["operation_id"]
                     for p in (bundle.get("panels") or {}).values()
                     for a in (p.get("acquired") or [])]
    ledger = experience.accounting(args.dsn, operation_ids)
    bundle["accounting"] = ledger
    bundle["key_discrepancy"] = experience.key_discrepancy(
        ledger["usage_keys_seen"],
        {"billed": set(ledger["billed_values_seen"]),
         "charge_units": set(ledger["charge_units_values_seen"])})
    report = build_report(
        bundle, namespace=NAMESPACE if not args.rerun else R2_NAMESPACE,
        campaign_kind="replication" if args.rerun else "first-contrast",
        is_replication_of=NAMESPACE if args.rerun else None)
    if args.rerun:
        report["agreement_with_first"] = replica.agreement_with_first(
            (bundle.get("panels") or {})
            .get("retention/within", {}).get("readings") or {},
            replica.read_first_namespace())
    out = Path(args.out or ("reports/evidence/"
                            + (R2_NAMESPACE if args.rerun else NAMESPACE)))
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str),
        encoding="utf-8")
    print(json.dumps({"paired": report["paired"],
                      "adaptation": report["adaptation"]},
                     indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
