"""Regenerate the E3 store witness (B1 / N-300) and the run digest (B5 / N-79).

Writes new files. It never writes to `reports/evidence/inv_r1_e3_selection/`
and never writes to `reports/evidence/inv_r1_e3_ladder/`, because those bytes
are the only surviving evidence that the defects existed. `reports/STAGE-09-
EVIDENCE-FINDINGS.md` is the write-up that must outlive the artifacts.

The committed generator is `experiments/ad01/s09_e3_selection.py:419`
`store_witness`, reached through `write_sever_evidence` at line 517. Measured
against it on an isolated database:

| | committed `e3-store-witness.json` | this generator |
|---|---|---|
| connected `bindings` | 5 | 5 |
| connected `receipts` | 5 | 5 |
| connected `operations_written_by_the_run` | 0 | 5 |
| connected `operations_in_store` | 0 | 5 |
| severed `bindings` | 0 | 0 |
| severed `receipts` | 4 | 0 |
| severed `operations_written_by_the_run` | 0 | 0 |

The severed arm is the structural half. `store_witness` at HEAD derives
`receipts` from `run.operations` at line 501, so a severed run — which never
constructs a recorder — yields an empty id list, and `read_back` at line 390
short-circuits on it. `bindings: []` and `receipts: []` now travel together.

The connected arm's `0` is the ordering half, and HEAD is not the code that
produced it. At `52235a6` the count was taken at line 529, the run at line 530
and the count again at line 532, all *before* the binding loop at line 534 that
called `broker.ensure_operation`. So the committed `0` is what that ordering
produces on a correct run. HEAD moved the writes inside the run
(`run_policy(..., dsn=dsn)` at line 444, decided through
`selection.DecisionRecorder` inside `selection._run_development`), so the count
is now taken across a run that has already written. The count reads 5 and
matches its own 5 receipts. That half needed a code change that already landed;
regenerating alone would not have fixed it, exactly as the write-up said.

`measure_digest` is not fixed here, and cannot be. It is
`selection.yield_measure_digest()` — the frozen measure set — so it is identical
across every artifact of the study by construction and cannot discriminate two
runs. B5's fix is `run_digest` beside it: a digest over the run's own operation
ids, which differ between the connected and severed arms and between this run
and the next. `measure_digest` is kept, labelled, and never used to relate two
files again.

Offline and deterministic in the sense that matters here: `live_dispatches: 0`.
Every decision is decided by the local agenda policy. Nothing calls the live
route, so this reads no credential and writes none.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from experiments.ad01 import s09_e3_selection as study
from experiments.ad01 import selection

B2_REPLACEMENT = "reports/evidence/inv_r1_e3_selection_regen_v2/e3-store-witness-v2.json"
B5_REPLACEMENT = "reports/evidence/inv_r1_e3_selection_regen_v2/e3-store-namespace-v2.json"

B1_FINDING = "B1 / N-300"
B5_FINDING = "B5 / N-79"
B6_FINDING = "B6 / N-80"


def run_digest(arm: dict) -> str:
    """A digest that varies between runs, unlike `measure_digest`.

    Over the operation ids the run actually reached, so the severed arm and
    the connected arm cannot collide and neither can two connected runs.
    Empty input digests to a fixed value, which is correct: a severed run
    reached nothing, and that is what its digest must say.
    """
    payload = {
        "world": arm["world"],
        "budget": arm["budget"],
        "sever": arm["sever"],
        "stop_reason": arm["stop_reason"],
        "decisions_made": arm["decisions_made"],
        "decision_targets": [d["target"] for d in arm["run_decisions"]],
        "operation_ids": sorted(
            r["operation_id"] for r in arm["receipts"]),
    }
    blob = json.dumps(payload, indent=1, sort_keys=True).encode("utf-8")
    return "sha256:%s" % hashlib.sha256(blob).hexdigest()


def arm_consistency(arm: dict) -> dict:
    """Every invariant B1 item 6 asks to be checkable, as a boolean.

    Checked rather than asserted, because the committed artifact failed these
    in three places at once and a field that cannot fail is not evidence.

    An invariant that only applies to one arm is only emitted for that arm. A
    check scored on the arm it cannot apply to is not a check, it is a false
    alarm, and a harness that produces those cannot be read as a verdict.
    """
    bindings = len(arm["bindings"])
    receipts = len(arm["receipts"])
    refused = len(arm["refused_decisions"])
    checks = {
        "arm": "severed" if arm["sever"] else "connected",
        "bindings": bindings,
        "receipts": receipts,
        "admitted_decisions": len(arm["admitted_decisions"]),
        "refused_decisions": refused,
        "decisions_made": arm["decisions_made"],
        "operations_written_by_the_run": arm["operations_written_by_the_run"],
        "operations_in_store": arm["operations_in_store"],
        "receipts_empty_iff_bindings_empty": (receipts == 0) == (bindings == 0),
        "written_matches_receipts": (
            arm["operations_written_by_the_run"] == receipts),
        "in_store_matches_receipts": (
            arm["operations_in_store"] == receipts),
        "refused_decisions_carry_no_operation_id": all(
            not d["operation_id"] for d in arm["refused_decisions"]),
        "every_decision_is_admitted_or_refused": (
            len(arm["admitted_decisions"]) + refused
            == len(arm["run_decisions"])),
    }
    if arm["sever"]:
        checks["severed_admits_nothing"] = not arm["admitted_decisions"]
        checks["severed_refuses_every_decision"] = refused > 0
    else:
        checks["connected_admits_every_decision"] = (
            len(arm["admitted_decisions"]) == len(arm["run_decisions"]))
        checks["connected_refuses_nothing"] = refused == 0
    return checks


def all_hold(checks: list) -> bool:
    return all(v for check in checks for k, v in check.items()
               if isinstance(v, bool))


def build(dsn: str, world: int, budget: int) -> dict:
    """Run both arms through the committed generator and judge the result."""
    connected = study.store_witness(dsn, world=world, budget=budget)
    severed = study.store_witness(dsn, world=world, budget=budget, sever=True)

    arms = {"connected": connected, "severed": severed}
    for arm in arms.values():
        arm["run_digest"] = run_digest(arm)

    checks = [arm_consistency(connected), arm_consistency(severed)]
    digests = {name: arm["run_digest"] for name, arm in arms.items()}
    return {
        "generated_by": "experiments/regen_v2/regen_e3_store_witness.py",
        "underlying_generator": (
            "experiments/ad01/s09_e3_selection.py:419 store_witness"),
        "finding": B1_FINDING,
        "world": world,
        "budget": budget,
        "live_dispatches": 0,
        "regenerated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
        "connected": connected,
        "severed": severed,
        "consistency_checks": checks,
        "every_consistency_check_holds": all_hold(checks),
        "run_digest_disambiguates": len(set(digests.values())) == 2,
        "run_digests": digests,
        "measure_digest_is_shared_by_construction": (
            connected["measure_digest"] == severed["measure_digest"]),
        "what_this_does_not_fix": [
            "measure_digest is selection.yield_measure_digest(), the frozen "
            "measure set, so it is identical across every artifact of the "
            "study by construction. It is published here only to name the "
            "value the committed files share, and it must not be used to "
            "relate two files. run_digest is the field that varies.",
            "operations_in_store is this run's own write count, not a "
            "store-wide count(*), so it cannot see a foreign lane's row. "
            "That is the N-301 correction and it is scoped to the run, not "
            "to the study.",
        ],
    }


def namespace_ledger(payload: dict) -> dict:
    """B5: one namespace, one current witness, and the succession recorded.

    B5 found five files sharing one `measure_digest` while reporting two
    different values of `operations_written_by_the_run`. This is the ledger
    that names which file is current and which ones it supersedes, so the
    question can be answered from a file rather than from commit order.
    """
    committed = {
        "reports/evidence/inv_r1_e3_selection/e3-store-witness.json": {
            "commit": "52235a6",
            "connected_operations_written_by_the_run": 0,
            "severed_receipts": 4,
            "defect": "B1 / N-300 and B5 / N-79",
        },
        "reports/evidence/inv_r1_e3_selection/e3-admitted-operations.json": {
            "commit": "a3b6cae",
            "connected_operations_written_by_the_run": 5,
            "defect": "shares the measure_digest with the witness above "
                      "while reporting a different value for the same field",
        },
        "reports/evidence/inv_r1_e3_selection/e3-sever-control.json": {
            "commit": "52235a6",
            "connected_operations_written_by_the_run": 0,
            "severed_receipts": 4,
            "defect": "duplicates both arms of the witness above, including "
                      "the contradiction",
        },
        "reports/evidence/inv_r1_e3_selection/e3-crossover.json": {
            "commit": "254f43e",
            "defect": "B6 / N-80 — the ladder, withdrawn; see "
                      "reports/evidence/inv_r1_e3_selection/RETRACTED.md "
                      "cause 1. Annotated, not deleted.",
        },
        "reports/evidence/inv_r1_e3_ladder/e3-postfix-ladder.json": {
            "commit": "3c1e5c5",
            "defect": "B6 / N-80 — $.committed_ladder re-embeds the "
                      "withdrawn ladder with no status key. Annotated, not "
                      "deleted: it is the pre-fix/post-fix bridge.",
        },
    }
    current = B2_REPLACEMENT
    return {
        "finding": B5_FINDING,
        "current_witness": current,
        "supersedes": {
            "reports/evidence/inv_r1_e3_selection/e3-store-witness.json":
                current,
            "reports/evidence/inv_r1_e3_selection/e3-sever-control.json":
                current,
        },
        "related_but_not_superseded": {
            "reports/evidence/inv_r1_e3_selection/e3-admitted-operations.json":
                "kept. It is a descendant commit and reports 5 against the "
                "witness's 0. The current witness agrees with it, so the "
                "succession is settled rather than merely asserted.",
        },
        "annotated_not_superseded": {
            "reports/evidence/inv_r1_e3_selection/e3-crossover.json": B6_FINDING,
            "reports/evidence/inv_r1_e3_ladder/e3-postfix-ladder.json": B6_FINDING,
        },
        "committed_files": committed,
        "measure_digest_shared_by": sorted({
            path for path, entry in committed.items()
            if "e3-admitted" in path or "store-witness" in path
            or "sever-control" in path
        }),
        "measure_digest_value": payload["connected"]["measure_digest"],
        "run_digests": payload["run_digests"],
        "what_this_does_not_fix": [
            "The shared measure_digest is still shared. It cannot be made to "
            "vary without changing what it measures, which is the frozen "
            "measure set, and the measure set is frozen by design. The fix "
            "is run_digest beside it, not a change to the freeze.",
        ],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=os.path.join(
        "reports", "evidence", "inv_r1_e3_selection_regen_v2"))
    parser.add_argument("--dsn", default=os.environ.get(
        "SETTLEMENT_TEST_DSN", ""))
    parser.add_argument("--world", type=int, default=0)
    parser.add_argument("--budget", type=int, default=40)
    args = parser.parse_args(argv)
    if not args.dsn:
        raise SystemExit(
            "a migrated disposable dsn is required: --dsn or "
            "SETTLEMENT_TEST_DSN")

    selection.assert_measure_freeze()
    payload = build(args.dsn, args.world, args.budget)
    payload["namespace_ledger"] = namespace_ledger(payload)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    witness = out / "e3-store-witness-v2.json"
    witness.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    print(json.dumps({
        "written": str(witness),
        "connected_bindings": len(payload["connected"]["bindings"]),
        "connected_receipts": len(payload["connected"]["receipts"]),
        "connected_operations_written_by_the_run":
            payload["connected"]["operations_written_by_the_run"],
        "severed_bindings": len(payload["severed"]["bindings"]),
        "severed_receipts": len(payload["severed"]["receipts"]),
        "every_consistency_check_holds":
            payload["every_consistency_check_holds"],
        "run_digest_disambiguates": payload["run_digest_disambiguates"],
        "live_dispatches": payload["live_dispatches"],
    }, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
