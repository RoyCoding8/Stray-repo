"""Does the frozen qualification gate pass on the frozen panel, under WSL?

A replication that cannot show its own instrument discriminating before it
dispatches has no verdict to trust afterwards. `run_campaign` refuses unless
`qualify_instrument(...)["separates_reader_from_blind"]`, so this decides
whether the frozen campaign is runnable at all, before any call.

Also checks the one question that decides whether a campaign-side fix is
possible at all: do `Reading.as_dict()` rows carry the keys `paired_report`
reads, where `reading_row` does not?
"""

from __future__ import annotations

import json
import sys
from typing import Any, Mapping

from . import e2_replication as replica
from . import learner
from . import worlds


def gate(*, authority: Mapping[str, Any]) -> dict:
    """Qualify the instrument on the frozen contrast's first target.

    `authority` is `{dsn, allocation_id}` for a store the caller holds, and
    it is required rather than optional because qualifying the instrument
    steps five policies, and stepping policy source is what the executor
    refuses without a store. It ran with none, so every row came back
    unscored and `separates_reader_from_blind` answered from nothing.
    """
    body = replica.contrast_block()
    task = worlds.load_task(worlds.FROZEN_DIR, body["target_task_ids"][0])
    arm = replica.build_arm(replica.ARM_RELEVANT, task,
                            source_task_ids=body["source_task_ids"],
                            filler_task_ids=body["filler_task_ids"],
                            visible=learner.visible_opportunities(0))
    result = replica.qualify_instrument(
        task, list(arm.get("observations") or []),
        eligible_methods=replica.eligible_for(task), authority=authority)
    return result


def as_dict_compatibility() -> dict:
    """Can a campaign keep `Reading.as_dict()` and reuse the frozen estimator?

    `paired_report` reads `normalized_reduction` and `action`. `reading_row`
    writes neither. `Reading.as_dict` carries both. If a campaign-side run
    keeps the `Reading` instead of the lossy projection, the frozen
    `paired_report` works unchanged, and the campaign needs no second
    estimator and no edit to a module it does not own.
    """
    row = {"scored": True, "verdict": "preserved", "candidate_measure": 3,
           "initial_measure": 13, "reason": "ok-preserved",
           "normalized_reduction": (13 - 3) / 13, "score": 1.0}
    return {
        "as_dict_fields_required_by_paired_report": {
            "normalized_reduction": row["normalized_reduction"],
            "action": {"inputs": {"method_id": "seed-sw-greedy",
                                  "max_queries": 8}},
        },
        "reading_row_fields": sorted(_reading_row_fields()),
        "reading_row_satisfies_paired_report": {
            name: (name in _reading_row_fields())
            for name in ("normalized_reduction", "action")},
        "as_dict_satisfies_paired_report": {
            name: (name in _as_dict_fields())
            for name in ("normalized_reduction", "action")},
        "conclusion": "as_dict carries both keys, so the frozen"
                      " `paired_report` runs on a campaign-side run that"
                      " keeps the Reading. The defect is a lossy projection"
                      " in the campaign, not a misreading estimator.",
    }


def _reading_row_fields() -> set:
    import inspect
    import re

    return set(re.findall(r'"(\w+)":', inspect.getsource(replica.reading_row)))


def _as_dict_fields() -> set:
    import inspect
    import re

    from . import s09_e2_scored as scored

    return set(re.findall(r'"(\w+)":', inspect.getsource(scored.Reading.as_dict)))


def main() -> int:
    from . import s09_run_isolation as isolation
    from settlement import authority as settlement_authority

    admin = isolation.admin_dsn()
    database = isolation.create_disposable_db("e2contrastgate",
                                              admin_dsn=admin)
    try:
        handle = settlement_authority.authorize_study(
            database.dsn, isolation.study_root_for("e2contrastgate"),
            authorized=1_000_000,
            allocation_id="e2contrastgate-alloc",
            ceilings={"sandbox_calls": 10_000, "model_calls": 1_000})
        result = gate(authority={"dsn": database.dsn,
                                 "allocation_id": handle.allocation_id})
    finally:
        isolation.drop_disposable_db(database, admin_dsn=admin)
    out = {
        "gate_passes": bool(result.get("separates_reader_from_blind")),
        "rows": {name: row for name, row in result.items()
                 if isinstance(row, dict) and "score" in row},
        "separates_reader_from_blind": result["separates_reader_from_blind"],
        "prompted_shape_earns_evidence": result["prompted_shape_earns_evidence"],
        "echo_confound": result["echo_confound"]["cells"],
        "echo_gap_relevant": result["echo_confound"]["echo_gap_relevant"],
        "echo_gap_none": result["echo_confound"]["echo_gap_none"],
        "as_dict_compatibility": as_dict_compatibility(),
    }
    json.dump(out, sys.stdout, indent=2, sort_keys=True, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
