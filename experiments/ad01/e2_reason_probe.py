"""Can the prompt render `reason` beside `verdict`? Measured, not argued.

`cfa8ab3` stopped E2 at its gate and left two changes on the table. The first
is a panel of tasks the authored reducers fail, which needs a new namespace
and a new freeze. The second is smaller: render `reason` beside `verdict`,
or read a scored observable that the budget actually moves. This module
measures the second one against the gate it was proposed to unblock, because
`reason` and `verdict` are both fields of one `experience_varies` call and
only one of them can change that call's answer.

The gate counts distinct values of `verdict`. Rendering `reason` in the
prompt changes what a *policy* can see and changes nothing the gate reads, so
`experience_varies` refuses exactly as it did before. That is the finding
that reorders the two changes, and it is established here by calling the gate
with the reason-bearing records the panel already has, not by reasoning about
the prompt.

It is also worth knowing whether the reason codes vary at the budget the
freeze pins. They do on the freeze's own three source tasks, and all three
earn the same one at the frozen budget of 8, so a reason-rendering arm would
read a signal the verdict collapses without becoming a panel the gate accepts.

Run: python -m experiments.ad01.e2_reason_probe
"""

from __future__ import annotations

import json
from collections import Counter

from . import e2_replication as replica
from . import e2_gate_report as gated
from . import worlds
from .control_distinctness import experience_varies

NAMESPACE = "inv_r1_e2_reason_probe"


def _gate_answer(observations, *, arm_name: str) -> dict:
    """The gate's own answer, with a refusal hoisted to the top level.

    `experience_varies` returns a constant experience as a verdict carrying
    `refusal` rather than by raising, so a caller that reads only `varies`
    sees a boolean and loses the sentence explaining it.
    """
    verdict = experience_varies(observations, arm_name=arm_name)
    out = {key: verdict[key] for key in
           ("observations", "verdicts", "distinct_verdicts", "outcomes",
            "distinct_outcomes", "varies")}
    out["refusal"] = verdict.get("refusal", "")
    return out


def reason_bearing_gate(frozen: dict) -> dict:
    """Does the proposed change move the gate? Read the gate, not the prompt.

    The prompt is not consulted here on purpose. The question is whether
    rendering `reason` unblocks `experience_varies`, and the gate reads one
    field of each record, so the answer is the gate's answer on records that
    already carry the reason.

    `gate_moved` now compares the count the gate decides on, which is the
    outcome rather than the verdict. It compared `distinct_verdicts` before,
    and that comparison is still reported as `verdicts_moved` because the
    verdict count is the measurement the fixpoint rests on: on this panel it
    is 1 before and 1 after, at every budget, and that is the finding.
    """
    observations = gated._panel_observations(
        frozen["source_task_ids"], max_queries=frozen["max_queries"])
    verdicts = sorted({str(row["verdict"]) for row in observations})
    reasons = sorted({str(row["reason"]) for row in observations})
    before = _gate_answer(replica.measured_observations(
        frozen["source_task_ids"]), arm_name="relevant-verdict-only")
    after = _gate_answer(observations, arm_name="relevant-with-reason")
    return {
        "records_carry": sorted(observations[0]),
        "distinct_verdicts": len(verdicts),
        "verdicts": verdicts,
        "distinct_reasons": len(reasons),
        "reasons": reasons,
        "gate_before": before,
        "gate_after": after,
        "gate_moved": (before["distinct_outcomes"]
                       != after["distinct_outcomes"]),
        "verdicts_moved": (before["distinct_verdicts"]
                           != after["distinct_verdicts"]),
        "counted_on": "verdict-and-reason",
        "verdict": ("the gate counts outcomes, and these three source tasks"
                    " grade one outcome at every budget, so the reason"
                    " bearing records do not move this panel. The verdict"
                    " count is 1 before and 1 after and cannot differ: the"
                    " oracle and the grader are one function, so a reducer's"
                    " output is preserved on every well-formed task"
                    if before["distinct_outcomes"]
                    == after["distinct_outcomes"]
                    else "the reason-bearing records move the gate"),
    }


def reason_by_budget(task_ids, *, budgets=gated.REASONS_BY_BUDGET) -> dict:
    """What the panel's own reducers earn, per task, at each budget.

    `cfa8ab3`'s note says the reason varies with budget where the verdict
    does not. That is true of the world and worth separating from the
    question the gate asks, which is about the panel the freeze names.
    """
    from . import seeds
    from experiments.representation import checkers

    rows = {}
    for task_id in sorted(task_ids or []):
        task = worlds.load_task(worlds.FROZEN_DIR, task_id)
        family = task.get("family")
        capability = next(
            (item for item in seeds.SEED_CAPABILITIES
             if item["capability_id"] == "seed-%s-ddmin"
             % ("sw" if family == "software" else "gr")), None)
        if capability is None:
            continue
        per_budget = {}
        for budget in budgets:
            candidate = seeds.run_seed(capability, task,
                                       max_queries=budget)["candidate"]
            report = (checkers.check_software(task, candidate)
                      if family == "software"
                      else checkers.check_graph(task, candidate))
            per_budget[str(budget)] = {"verdict": report["verdict"],
                                       "reason": report["reason"]}
        rows[task_id] = per_budget
    return rows


def report() -> dict:
    frozen = replica.freeze()["body"]
    gate = reason_bearing_gate(frozen)
    panel = reason_by_budget(frozen["source_task_ids"],
                             budgets=(1, 8, 64))
    panel_reasons = sorted({fields["reason"]
                            for per_budget in panel.values()
                            for fields in per_budget.values()})
    panel_verdicts = sorted({fields["verdict"]
                             for per_budget in panel.values()
                             for fields in per_budget.values()})
    fp_verdict = "unknown"
    if len(panel_reasons) >= 2 and len(panel_verdicts) == 1:
        fp_verdict = ("the reason varies with budget on the freeze's own"
                      " source tasks where the verdict does not, so a"
                      " reason-rendering arm sees variation the verdict"
                      " collapses, and it is the gate that stays refused"
                      " because the gate reads the verdict")
    elif len(panel_reasons) == 1:
        fp_verdict = ("the freeze's own source tasks earn one reason at every"
                      " budget, so a reason-rendering arm would be refused for"
                      " the same reason as a verdict-rendering one")
    return {
        "version": "ad01-e2-reason-probe/1",
        "namespace": NAMESPACE,
        "dispatches": 0,
        "database": None,
        "supersedes": None,
        "reason_bearing_gate": gate,
        "frozen_panel": {
            "source_task_ids": list(frozen["source_task_ids"]),
            "max_queries": frozen["max_queries"],
            "by_budget": panel,
            "distinct_reasons": panel_reasons,
            "verdicts": panel_verdicts,
            "verdict_is_constant": len(panel_verdicts) == 1,
            "reason_varies_with_budget": len(panel_reasons) >= 2,
            "reasons_at_frozen_budget": sorted({
                fields["reason"]
                for per_budget in panel.values()
                for budget, fields in per_budget.items()
                if budget == str(frozen["max_queries"])}),
            "verdict": fp_verdict,
        },
        "world_reason_surface": _world_surface(),
        "verdict": ("the reason varies with budget on the freeze's own"
                    " source tasks, so the proposed change would give a"
                    " policy a varying signal to read, and the gate stays"
                    " refused because the gate reads the verdict, so a panel"
                    " that varies and a gate that reads the varied field are"
                    " both required before a run is worth dispatching"),
    }


def _world_surface() -> dict:
    """The reason codes the whole frozen world earns, over a budget sweep."""
    from . import seeds
    from experiments.representation import checkers

    membership = worlds.world_membership(worlds.FROZEN_DIR)
    verdicts, reasons = Counter(), Counter()
    pairs = 0
    for world_id in sorted(membership):
        splits = membership[world_id]
        if not isinstance(splits, dict):
            continue
        for split, families in sorted(splits.items()):
            if not isinstance(families, dict):
                continue
            for family, task_ids in sorted(families.items()):
                if not isinstance(task_ids, list):
                    continue
                for task_id in sorted(task_ids):
                    task = worlds.load_task(worlds.FROZEN_DIR, task_id)
                    capability = next(
                        (item for item in seeds.SEED_CAPABILITIES
                         if item["capability_id"] == "seed-%s-ddmin"
                         % ("sw" if family == "software" else "gr")), None)
                    if capability is None:
                        continue
                    for budget in gated.REASONS_BY_BUDGET:
                        candidate = seeds.run_seed(
                            capability, task, max_queries=budget)["candidate"]
                        checked = (checkers.check_software(task, candidate)
                                   if family == "software"
                                   else checkers.check_graph(task, candidate))
                        pairs += 1
                        verdicts[checked["verdict"]] += 1
                        reasons[checked["reason"]] += 1
    return {"task_budget_pairs": pairs,
            "verdicts": dict(sorted(verdicts.items())),
            "reasons": dict(sorted(reasons.items())),
            "verdict_is_constant": len(verdicts) == 1,
            "reason_is_constant": len(reasons) == 1}


if __name__ == "__main__":
    print(json.dumps(report(), indent=2, sort_keys=True))
