"""A campaign-side diagnosis of the E2 instrument, before any dispatch.

Reads the frozen `e2_replication` module and records what it can and cannot
measure on the panel this lane is assigned. Every number here is derived by
running the campaign's own code offline; nothing is dispatched.

Run under WSL: `python3 -m experiments.ad01.e2_contrast_diagnose`.
"""

from __future__ import annotations

import json
import sys

from . import e2_replication as replica
from . import learner
from . import s09_e2_scored as scored
from . import worlds

TARGETS = ("ad01-w0-within-sw-00", "ad01-w0-within-sw-01",
           "ad01-w0-within-sw-02")


def read_row_fields(reading_row_fn) -> list:
    """The keys `reading_row` actually writes, read off its own dict literal.

    Not by calling it: it needs a `Reading`, and a `Reading` needs a child.
    The function's return literal is the contract `paired_report` consumes, so
    this is the same field list a call would have produced.
    """
    import inspect
    import re

    body = inspect.getsource(reading_row_fn)
    return sorted(set(re.findall(r'"(\w+)":', body)))


def defect_graded_outcome_uniformity() -> dict:
    """Do the relevant arm's records differ in graded outcome or only in id?"""
    body = replica.contrast_block()
    relevant = replica.measured_observations(body["source_task_ids"])
    filler = replica.measured_observations(body["filler_task_ids"])

    def profile(rows):
        return {
            "records": len(rows),
            "distinct_verdicts": sorted({str(r.get("verdict")) for r in rows}),
            "distinct_reasons": sorted({str(r.get("reason")) for r in rows}),
            "distinct_reductions": sorted({round(float(r.get("reduction") or 0.0), 6)
                                            for r in rows}),
            "distinct_task_ids": len({str(r.get("task_id")) for r in rows}),
            "per_record": [{"task_id": r.get("task_id"),
                            "verdict": r.get("verdict"),
                            "reason": r.get("reason"),
                            "reduction": r.get("reduction")} for r in rows],
        }

    relevant_profile = profile(relevant)
    filler_profile = profile(filler)
    return {
        "relevant": relevant_profile,
        "filler_control": filler_profile,
        "relevant_graded_outcome_is_uniform": len(relevant_profile["distinct_reasons"]) <= 1,
        "filler_graded_outcome_varies": len(filler_profile["distinct_reasons"]) > 1,
        "reading": "the graded outcome is the checker's (verdict, reason) pair."
                    " `normalized_reduction` is carried in the record but is"
                    " not a graded outcome, and it is dropped by the packet"
                    " projection, so a policy never receives it.",
    }


def defect_estimator_field_mismatch() -> dict:
    """Does `paired_report` read keys `reading_row` writes?"""
    written = read_row_fields(replica.reading_row)
    consumed = {
        "normalized_reduction": replica._reduction_of(
            {"normalized_reduction": 0.42}),
        "action.inputs": replica._decision_of(
            {"action": {"inputs": {"method_id": "seed-sw-greedy",
                                   "max_queries": 4}}}),
    }
    return {
        "reading_row_writes": written,
        "normalized_reduction": {
            "read_by": "_reduction_of", "present_in_reading_row":
            replica.NORMALIZED_REDUCTION in written,
            "value_when_absent": consumed["normalized_reduction"],
        },
        "action": {
            "read_by": "_decision_of", "present_in_reading_row": "action" in written,
            "value_when_absent": consumed["action.inputs"],
        },
        "consequence": "every paired delta is 0.0 by arithmetic and every"
                       " decision compares {'', None} with {'', None}, so"
                       " `differs` is False everywhere. The contrast computes"
                       " nothing, in either direction.",
        "reading_as_dict_carries_both": sorted(
            k for k in scored.Reading.__dataclass_fields__
            if k in ("normalized_reduction", "action")),
    }


def defect_view_projection() -> dict:
    """What does a policy actually receive, and what did the prompt promise?"""
    body = replica.contrast_block()
    task = worlds.load_task(worlds.FROZEN_DIR, body["target_task_ids"][0])
    arm = replica.build_arm(replica.ARM_RELEVANT, task,
                            source_task_ids=body["source_task_ids"],
                            filler_task_ids=body["filler_task_ids"],
                            visible=learner.visible_opportunities(0))
    observations = list(arm.get("observations") or [])
    view = scored.build_views(task, observations,
                              eligible_methods=replica.eligible_for(task),
                              remaining={"steps": 1})
    prompt = replica.prompt_for(replica.ARM_RELEVANT, task, arm)
    line = next((ln for ln in prompt.splitlines()
                 if ln.startswith("Prior observations:")), "")
    projected = list(view["scored"].get("observations") or [])
    return {
        "record_carries": sorted(observations[0]) if observations else [],
        "prompt_shows": line[:600],
        "view_delivers": sorted(projected[0]) if projected else [],
        "dropped_before_the_policy": sorted(
            set(observations[0]) - set(projected[0])) if (observations and projected) else [],
        "verdicts_the_policy_sees": sorted({str(o.get("verdict")) for o in projected}),
        "details_the_policy_sees": sorted({str(o.get("detail")) for o in projected}),
        "reading": "the prompt promises `reason` and the view drops it, so a"
                   " policy reading the verdicts sees one constant. This is"
                   " the same three-point class of drop the prior repair"
                   " fixed on the prompt side, left open on the view side.",
    }


def panel_headroom() -> dict:
    """How far can the benefit metric move on this panel, at all?

    Derived from the checker's own reports on the authored methods, offline.
    A contrast whose arms can only pick between two methods needs to know
    which method each choice reaches, and whether the zero-information
    default is already the better one.
    """
    from . import seeds

    rows = []
    for split in (replica.TARGET_SPLIT, "transfer"):
        for task_id in worlds.world_membership(worlds.FROZEN_DIR)["0"][split]["software"]:
            task = worlds.load_task(worlds.FROZEN_DIR, task_id)
            entry = {"split": split, "task_id": task_id, "methods": {}}
            for capability_id in ("seed-sw-ddmin", "seed-sw-greedy"):
                capability = next(c for c in seeds.SEED_CAPABILITIES
                                  if c["capability_id"] == capability_id)
                result = seeds.run_seed(capability, task,
                                        max_queries=replica.MAX_QUERIES)
                report = replica._grade(task, result["candidate"])
                entry["methods"][capability_id] = {
                    "normalized_reduction": replica._normalized_reduction(report),
                    "verdict": report["verdict"], "reason": report["reason"],
                    "queries": int(result.get("queries") or 0),
                }
            best = max(entry["methods"].items(),
                       key=lambda kv: kv[1]["normalized_reduction"])
            default = entry["methods"]["seed-sw-ddmin"]
            entry["best_method"] = best[0]
            entry["default_method"] = "seed-sw-ddmin"
            entry["default_is_best"] = best[0] == "seed-sw-ddmin"
            entry["default_shortfall"] = round(
                best[1]["normalized_reduction"]
                - default["normalized_reduction"], 6)
            rows.append(entry)
    within = [r for r in rows if r["split"] == replica.TARGET_SPLIT]
    return {
        "rows": rows,
        "default_is_best_on": sum(1 for r in rows if r["default_is_best"]),
        "total_tasks": len(rows),
        "max_positive_delta_attemptable": max(
            (r["default_shortfall"] for r in rows), default=0.0),
        "verdict": "the zero-information default (the first eligible method,"
                   " seed-sw-ddmin) is the better method on every task in the"
                   " frozen panel, so a no-experience arm that names the"
                   " default has already spent the available headroom and the"
                   " benefit metric has nothing left for experience to win."
                   if all(r["default_is_best"] for r in rows) else
                   "the default is not uniformly best, so a positive delta is"
                   " structurally attainable on this panel",
        "consequence": "the contrast can only move the metric off the default."
                       " A negative delta is attainable; a positive one is not.",
    }


def main() -> int:
    out = {
        "diagnosed_offline": True,
        "dispatches": 0,
        "defect_graded_outcome_uniformity": defect_graded_outcome_uniformity(),
        "defect_estimator_field_mismatch": defect_estimator_field_mismatch(),
        "defect_view_projection": defect_view_projection(),
        "panel_headroom": panel_headroom(),
    }
    json.dump(out, sys.stdout, indent=2, sort_keys=True, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
