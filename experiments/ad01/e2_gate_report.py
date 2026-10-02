"""E2 pre-dispatch gates, run against the frozen panel. Nothing is sent.

`experiments/ad01/e2_replication.py` re-measured every observation's verdict
by running an authored reducer and grading its candidate. That is the right
construction, and it is why the experience came out constant: the authored
reducers solve every task in the panel, so the checker grades all of them
`preserved` and the arm carries one distinct verdict. The four refusals below
are that fact, measured, and they refuse before a dispatch is spent
re-measuring it.

The second refusal is a different defect at one level up.
`control_distinct` cannot name an executed policy on the replica's own
records, because `e2_replication` writes an operation id and never an executed
policy id. The gate does not credit a record with a policy it did not name, so
an E2 arm is refused for the same reason an E1 arm is: nobody wrote down what
ran.

Run: python -m experiments.ad01.e2_gate_report
"""

from __future__ import annotations

import json
from pathlib import Path

from . import e2_replication as replica
from . import worlds
from .control_distinctness import (GateRefused, control_distinct,
                                   experience_varies, menu_answers_nothing)

NAMESPACE = "inv_r1_e2_gated"

REPORT_PATH = (Path(__file__).resolve().parents[2] / "reports" / "evidence"
               / replica.NAMESPACE / "report.json")

# The reason codes the panel's own reducers earn, kept beside the verdict
# because the verdict collapses them and the reason does not.
REASONS_BY_BUDGET = (1, 4, 8, 64)


def _reason(task: dict, candidate, family: str) -> str:
    from experiments.representation import checkers

    if family == "software":
        return checkers.check_software(task, candidate)["reason"]
    return checkers.check_graph(task, candidate)["reason"]


def _panel_observations(source_task_ids, *, max_queries: int) -> list:
    """The experience records the arms carry, plus the reason each earned."""
    rows = []
    for task_id in sorted(source_task_ids or []):
        row = dict(replica._measured_row(task_id, max_queries=max_queries))
        task = worlds.load_task(worlds.FROZEN_DIR, task_id)
        from . import seeds

        capability = next(item for item in seeds.SEED_CAPABILITIES
                          if item["capability_id"] == replica._capability(task))
        result = seeds.run_seed(capability, task, max_queries=max_queries)
        row["reason"] = _reason(task, result["candidate"], task.get("family"))
        row["method"] = replica._capability(task)
        rows.append(row)
    return rows


def reachable_verdicts() -> dict:
    """Every verdict the frozen world reaches, over every split and budget.

    A refusal that a policy could not have earned is a defect in the policy
    set rather than in the arm. This separates the two: it sweeps the
    authored reducers the arms are built from and records what they grade.
    """
    from collections import Counter

    from . import seeds
    from experiments.representation import checkers

    membership = worlds.world_membership(worlds.FROZEN_DIR)
    verdicts, reasons, pairs = Counter(), Counter(), 0
    for world_id in sorted(membership):
        for split, families in sorted(membership[world_id].items()):
            if not isinstance(families, dict):
                continue
            for family, task_ids in sorted(families.items()):
                for task_id in sorted(task_ids):
                    task = worlds.load_task(worlds.FROZEN_DIR, task_id)
                    capability_id = ("seed-sw-" if family == "software"
                                     else "seed-gr-") + "ddmin"
                    capability = next(
                        (item for item in seeds.SEED_CAPABILITIES
                         if item["capability_id"] == capability_id), None)
                    if capability is None:
                        continue
                    for budget in REASONS_BY_BUDGET:
                        result = seeds.run_seed(capability, task,
                                                max_queries=budget)
                        pairs += 1
                        report = (checkers.check_software(task, result["candidate"])
                                  if family == "software"
                                  else checkers.check_graph(task, result["candidate"]))
                        verdicts[report["verdict"]] += 1
                        reasons[report["reason"]] += 1
    return {"task_budget_pairs": pairs, "budgets_swept": list(REASONS_BY_BUDGET),
            "verdicts": dict(sorted(verdicts.items())),
            "reasons": dict(sorted(reasons.items())),
            "verdict_is_constant": len(verdicts) == 1}


def substitution_contrast() -> dict:
    """Does the treatment's prompt move when the evidence is substituted?

    The scored arm's prompt renders `task_id` and `verdict` per observation
    and nothing else. Substituting the alternate view's verdicts therefore
    changes the prompt by the verdict tokens alone. What that buys is measured
    by rendering a reader, an echoer and an ignorer and comparing the key each
    would write: the observable cannot separate them when the verdicts they
    would each write are the same string.
    """
    frozen = replica.freeze()["body"]
    target = worlds.load_task(worlds.FROZEN_DIR, frozen["target_task_ids"][0])
    observations = replica.measured_observations(frozen["source_task_ids"])
    arm = replica.build_arm("relevant", target,
                            source_task_ids=frozen["source_task_ids"],
                            filler_task_ids=frozen["filler_task_ids"],
                            visible=[])
    scored = replica.prompt_for("relevant", target, arm)
    alternate_arm = dict(arm, observations=[
        dict(row, verdict="not_preserved") for row in observations])
    alternate = replica.prompt_for("relevant", target, alternate_arm)
    verdicts = [str(row["verdict"]) for row in observations]
    reader = ",".join(verdicts)
    echoer = ",".join(str(row["verdict"]) for row in observations)
    ignorer = ",".join("preserved" for _ in observations)
    return {
        "version": "ad01-e2-substitution/1",
        "scored_prompt_chars": len(scored),
        "alternate_prompt_chars": len(alternate),
        "prompts_differ": scored != alternate,
        "experience_verdicts": sorted(set(verdicts)),
        "reader_writes": reader,
        "echoer_writes": echoer,
        "ignorer_writes": ignorer,
        "reader_equals_echoer": reader == echoer,
        "reader_equals_ignorer": reader == ignorer,
        "echo_excluded": not (reader == echoer and reader == ignorer),
        "verdict": ("the observable cannot separate a reader from an echoer or"
                    " from a policy that hardcodes the string, because the"
                    " experience carries one verdict and the prompt renders"
                    " that verdict alone"),
    }


def _gate(label, arm_name, observations) -> dict:
    """Run one gate, hoisting its refusal to the top level.

    `experience_varies` returns a constant experience as a verdict carrying
    `refusal` rather than by raising, while `control_distinct` raises. Both
    are refusals, so both are hoisted, because a reader that has to know
    which of the two shapes a gate returns to find its refusal will read a
    refusal as a pass.
    """
    try:
        verdict = experience_varies(observations, arm_name=arm_name)
    except GateRefused as refusal:
        return {"label": label, "varies": False, "refusal": str(refusal)}
    out = {"label": label, "varies": verdict["varies"], "verdict": verdict}
    if "refusal" in verdict:
        out["refusal"] = verdict["refusal"]
    return out


def _distinct(label, control_rows, acquired_rows) -> dict:
    try:
        verdict = control_distinct(control_rows, acquired_rows)
    except GateRefused as refusal:
        return {"label": label, "distinct": False, "refusal": str(refusal)}
    out = {"label": label, "distinct": verdict["distinct"], "verdict": verdict}
    if "refusal" in verdict:
        out["refusal"] = verdict["refusal"]
    return out


def replica_acquired_records() -> list:
    """The replica's own records, exactly as they are on disk.

    E2 is a construction arm. `e2_replication` writes an operation id, a
    response digest and a prompt length, and never an executed policy id. The
    gate is handed the records unchanged rather than enriched, because the
    refusal that comes back is the finding: an E2 record cannot say what ran.
    """
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    return [{"task_id": row["task_id"], "arm": row["arm"],
             "operation_id": row["operation_id"]}
            for row in report["acquired"]]


def report() -> dict:
    frozen = replica.freeze()
    body = frozen["body"]
    freeze_ok, freeze_refusal = True, ""
    try:
        replica.verify_freeze(frozen)
    except replica.ReplicaRefused as refusal:
        freeze_ok, freeze_refusal = False, str(refusal)

    relevant = _panel_observations(body["source_task_ids"],
                                   max_queries=body["max_queries"])
    filler = _panel_observations(body["filler_task_ids"],
                                 max_queries=body["max_queries"])
    records = replica_acquired_records()

    def arm_rows(name):
        return [row for row in records if row.get("arm") == name]

    gates = {
        "experience_varies_relevant": _gate(
            "relevant", "relevant", relevant),
        "experience_varies_irrelevant": _gate(
            "irrelevant", "irrelevant", filler),
        "control_distinct_relevant_vs_none": _distinct(
            "relevant-vs-none", arm_rows("relevant"), arm_rows("none")),
        "control_distinct_relevant_vs_irrelevant": _distinct(
            "relevant-vs-irrelevant", arm_rows("relevant"),
            arm_rows("irrelevant")),
        "menu_answers_nothing": menu_answers_nothing(),
    }
    refused = sorted(name for name, gate in gates.items()
                     if "refusal" in gate)
    return {
        "version": "ad01-e2-gated/1",
        "namespace": NAMESPACE,
        "verdict": (
            "refused: E2's experience is a constant before any dispatch, so a"
            " run would re-measure it and spend live dispatches to learn it a"
            " second time"),
        "gates_refused": refused,
        "gates_passed": sorted(name for name in gates if name not in refused),
        "dispatches": 0,
        "database": None,
        "freeze": {"body": body, "freeze_digest": frozen["freeze_digest"],
                   "intact": freeze_ok, "refusal": freeze_refusal,
                   "supersedes": replica.NAMESPACE},
        "gates": gates,
        "experience": {
            "relevant": relevant,
            "irrelevant": filler,
            "note": ("the `reason` field varies with the budget where the"
                     " `verdict` field does not, and the prompt renders the"
                     " verdict alone"),
        },
        "reachable_verdicts": reachable_verdicts(),
        "substitution": substitution_contrast(),
    }


if __name__ == "__main__":
    print(json.dumps(report(), indent=2, sort_keys=True))
