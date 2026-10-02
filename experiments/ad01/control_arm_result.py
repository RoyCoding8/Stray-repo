"""Turn a study run with a control arm into one result artifact.

The gates are read first and reported whatever they say. `control_distinct`
raising, refusing, or passing and `experience_varies` refusing are both
results, and a run that dispatched and produced records with one gate
refusing is worth more than a run that produced nothing.

What this writes, in a directory of its own under `reports/evidence/`:

`control_distinct.json`  the gate's full verdict on the two arms
`experience_varies.json` the same for the experience gate, with its numbers
`arms.json`              every row on both arms: the executed policy id, the
                         returned candidate's digest and size, the per-record
                         outcome, and the per-task comparison
`cost.json`              the run's spend in this repository's four separate
                         currencies
`summary.md`             the same, readable, with the tie or the difference

Nothing under `reports/evidence/` is read for anything but this run's own
outputs, and nothing there is written except into the new directory.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

CONTROL_ARM = "C"


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _size_of(row: dict) -> int:
    output = row.get("output") or {}
    if not isinstance(output, dict):
        return 0
    for key in ("ops", "vertices"):
        value = output.get(key)
        if isinstance(value, list):
            return len(value)
    return 0


def split_arms(records: list, *, control_arm: str = CONTROL_ARM) -> tuple:
    """The two arms, by what the record says about itself.

    A control record carries `study_arm`, which the study writes, because
    the control has no campaign and so no campaign id to be told apart by.
    Everything else is acquired.

    The acquired side arrives as two orderings, I and R, over the same
    tasks. Both are kept: they are two runs of the acquisition, and which
    one a control is compared against is a choice with an owner. The
    default here is I, the first ordering, and `split_acquired_orderings`
    exposes both so a reader can compare against either.
    """
    control = [r for r in records
               if str(r.get("study_arm") or "") == control_arm
               or str(r.get("arm") or "") == control_arm]
    acquired = [r for r in records if r not in control]
    return control, acquired


def split_acquired_orderings(acquired: list) -> dict:
    return {name: [r for r in acquired if str(r.get("arm")) == name]
            for name in sorted({str(r.get("arm")) for r in acquired})}


def arm_rows(records: list, *, control_arm: str = CONTROL_ARM) -> list:
    """One row per record: what it ran, what it returned, how it ended.

    `query_trace` rides along. The gate reads the walk to tell one method
    run twice from two methods that met on the same answer, and a result
    artifact that dropped it would leave the gate's own input in a
    scratch directory rather than beside the verdict that used it.
    """
    rows = []
    for record in records:
        output = record.get("output") or {}
        rows.append({
            "record_id": record.get("record_id"),
            "arm": record.get("study_arm") or record.get("arm"),
            "world": record.get("world"),
            "task_id": record.get("task_id"),
            "domain": record.get("domain"),
            "executed_policy_id": record.get("executed"),
            "executed_source": record.get("executed_source"),
            "strategy_named": _strategy(record.get("executed_source")),
            "candidate_digest": _digest(output),
            "candidate_size": _size_of(record),
            "initial_measure": record.get("initial_measure"),
            "final_measure": record.get("final_measure"),
            "normalized_reduction": record.get("normalized_reduction"),
            "verdict": record.get("verdict"),
            "status": record.get("status", "ok"),
            "fallback_reason": record.get("fallback_reason") or "",
            "witness_queries": (record.get("costs") or {}).get(
                "witness_queries"),
            "operation_ids": record.get("operation_ids") or [],
            "query_trace": record.get("query_trace"),
        })
    return rows


def _strategy(source) -> str:
    """The strategy a record's executed source names, read the gate's way."""
    from experiments.ad01 import control_distinctness
    return control_distinctness._strategy_of(
        {"executed_source": source} if isinstance(source, str) else {})


def per_task(control: list, acquired: list) -> list:
    """One row per paired task, with the difference the arms made."""
    def index(rows):
        out = {}
        for row in rows:
            out.setdefault(row["task_id"], []).append(row)
        return out

    left, right = index(control), index(acquired)
    out = []
    for task_id in sorted(set(left) & set(right)):
        for control_row in left[task_id]:
            for acquired_row in right[task_id]:
                out.append({
                    "task_id": task_id,
                    "domain": control_row["domain"],
                    "control_executed": control_row["executed_policy_id"],
                    "acquired_executed": acquired_row["executed_policy_id"],
                    "control_strategy": control_row["strategy_named"],
                    "acquired_strategy": acquired_row["strategy_named"],
                    "control_size": control_row["candidate_size"],
                    "acquired_size": acquired_row["candidate_size"],
                    "candidate_digest_equal":
                        control_row["candidate_digest"]
                        == acquired_row["candidate_digest"],
                    "control_reduction": control_row[
                        "normalized_reduction"],
                    "acquired_reduction": acquired_row[
                        "normalized_reduction"],
                })
    return out


def _mean(values: list):
    from fractions import Fraction
    if not values:
        return None
    return float(sum(Fraction(str(v)) for v in values) / len(values))


def utility(paired: list) -> dict:
    """The mean acquired-minus-control reduction, and what it means.

    A mean of exactly zero is a tie and is reported as one, with the
    per-task numbers beside it. This is `task_utility_verdict`'s own rule
    over the same records, computed here because the verdict layer wants a
    freeze and a construction block this run does not otherwise produce.
    """
    deltas = [row["acquired_reduction"] - row["control_reduction"]
              for row in paired
              if row["control_reduction"] is not None
              and row["acquired_reduction"] is not None]
    mean = _mean(deltas)
    if mean is None:
        verdict = "NOT_COMPARABLE"
    elif mean == 0:
        verdict = "TIE"
    elif mean > 0:
        verdict = "ACQUIRED_WINS"
    else:
        verdict = "CONTROL_WINS"
    return {"value": verdict, "mean_acquired_minus_control": mean,
            "paired_tasks": len(deltas),
            "per_task_deltas": {row["task_id"]: (
                None if row["control_reduction"] is None
                or row["acquired_reduction"] is None
                else row["acquired_reduction"] - row["control_reduction"])
                for row in paired}}


def gate_control_distinct(control: list, acquired: list) -> dict:
    from experiments.ad01 import control_distinctness
    try:
        verdict = control_distinctness.control_distinct(control, acquired)
    except control_distinctness.GateRefused as refusal:
        return {"gate": "control_distinct", "distinct": False,
                "raised": True, "refusal": str(refusal)}
    out = {"gate": "control_distinct", "distinct": verdict["distinct"],
           "raised": False, "verdict": verdict}
    if "refusal" in verdict:
        out["refusal"] = verdict["refusal"]
    return out


def gate_experience(records: list, *, arm_name: str = "control") -> dict:
    """`experience_varies` over this run's own records.

    The gate wants observations, and a use record is an observation with a
    `verdict` on it. This is the E2 gate applied to the control arm's own
    evidence rather than to the E2 replica's, so the refusal or the pass is
    about the arm that ran.

    Two things the earlier version got wrong, both found by running it.

    **The reason was dropped.** A use record carries the checker's verdict but
    not its reason, and the reasons are what the panel's axis moves. The
    reason is re-derived here by grading the record's own returned candidate
    through the campaign's checker, which is the same call that produced the
    verdict, so the two cannot disagree and no new field has to be threaded
    through `run_use`. A record whose candidate cannot be regraded carries no
    reason, and the gate then counts its verdict alone, which is the honest
    reading of a record the checker could not be asked about.

    **A refusal was graded as an outcome.** `run_use` writes `verdict:
    "refused"` on a record whose policy raised, and that is not a grade from
    the checker's vocabulary at all. Counted as an outcome it made a dead arm
    look like a varied one: on this lane's first run on `ad01-exp-axis` the
    gate passed with outcomes `['preserved', 'refused']` while the 21 records
    that actually executed were all `preserved` and the verdict was one bit
    throughout. A gate that opens because an arm did not run is the defect
    this function exists to prevent, so a non-checker verdict is now a
    refusal of the whole experience rather than a second kind of outcome.
    """
    from experiments.representation import checkers
    from experiments.ad01 import control_distinctness

    observations = []
    for record in records:
        verdict = str(record.get("verdict") or "")
        if verdict not in checkers.PRESERVED:
            return {"gate": "experience_varies", "varies": False,
                    "raised": True,
                    "refusal": ("refused: the %s arm carries a record that"
                                " the checker did not grade (%r on %s), so"
                                " its experience is not a set of measured"
                                " outcomes" % (arm_name, verdict,
                                               record.get("task_id"))),
                    "non_checker_verdicts": sorted({
                        str(row.get("verdict") or "")
                        for row in records
                        if str(row.get("verdict") or "")
                        not in checkers.PRESERVED})}
        reason = _reason_of(record)
        observations.append({"task_id": record.get("task_id"),
                             "verdict": verdict,
                             "reason": reason,
                             "method": _strategy(record.get("executed_source"))})
    try:
        verdict = control_distinctness.experience_varies(
            observations, arm_name=arm_name)
    except control_distinctness.GateRefused as refusal:
        return {"gate": "experience_varies", "varies": False,
                "raised": True, "refusal": str(refusal)}
    out = {"gate": "experience_varies", "varies": verdict["varies"],
           "raised": False, "verdict": verdict}
    if "refusal" in verdict:
        out["refusal"] = verdict["refusal"]
    return out


def _reason_of(record: dict) -> str:
    """The checker's reason for the candidate this record returned.

    Re-derived rather than read, because `run_use` does not write it. The
    candidate is the record's own `output` and the task is the frozen one, so
    this is the same grading the verdict came from and a disagreement is not
    possible. Returns the empty string for a record that cannot be graded,
    which the gate reads as "no reason" rather than as a placeholder.
    """
    from experiments.representation import checkers
    from experiments.ad01 import experience_axis, worlds

    task_id = str(record.get("task_id") or "")
    output = record.get("output")
    if not task_id or not isinstance(output, dict):
        return ""
    for root in (worlds.FROZEN_DIR, experience_axis.FROZEN_DIR):
        try:
            task = worlds.load_task(root, task_id)
        except (KeyError, OSError, ValueError):
            continue
        family = task.get("family")
        if family == "software":
            return str(checkers.check_software(task, output)["reason"])
        return str(checkers.check_graph(task, output)["reason"])
    return ""


def cost_currencies(*, dsn: str | None, study_root: str) -> dict:
    """The run's spend, in this repository's four separate currencies.

    They are separate and they are not the same number, so they are
    reported separately and none is derived from another:

    `dispatch_allowance`    operations the study's allocations actually
                            hold, counted from the store rather than from
                            the run's own tally
    `reservation_allowance` internal units the study was authorized with
    `provider_billing`      what the provider charged, or NOT_REPORTED /
                            UNMEASURED. Never zero for a spend that cannot
                            be read: a lost response is uncertain, not
                            free.
    `internal_held_units`   units the study's allocation still holds

    A store that cannot be read reports UNMEASURED with the exception, not
    a zero. Every figure here is either measured or marked.
    """
    from settlement import authority, store
    from scripts import inv01_study as study

    campaigns = study._v1_campaign_count(6)
    out = {
        "dispatch_allowance": {"status": "UNMEASURED"},
        "reservation_allowance": {
            "status": "REPORTED",
            "study_units_authorized": study._v1_study_units(campaigns),
            "campaign_units": study._v1_campaign_units(),
            "campaigns": campaigns,
            "source": "s09_cap_sheet unit allowance times the campaign"
                      " count plus one per control arm",
        },
        "provider_billing": {
            "status": "NOT_REPORTED",
            "reason": "recording doubles bill false; the run made no"
                      " provider call to bill",
            "note": "a spend that cannot be read is UNMEASURED, never zero",
        },
        "internal_held_units": {"status": "UNMEASURED"},
    }
    if not dsn:
        out["dispatch_allowance"]["reason"] = "no dsn supplied"
        out["internal_held_units"]["reason"] = "no dsn supplied"
        return out
    try:
        handle = authority.bind_study(dsn, study_root)
    except Exception as exc:
        for key in ("dispatch_allowance", "internal_held_units"):
            out[key]["reason"] = "study not bound: %s" % exc
        return out
    from psycopg.rows import dict_row
    from settlement import db
    try:
        with db.read_connect(dsn) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "WITH RECURSIVE kids (id) AS ("
                    " SELECT id FROM allocations WHERE id = %s"
                    " UNION SELECT a.id FROM allocations a"
                    " JOIN kids k ON a.parent_id = k.id)"
                    " SELECT o.id, o.payload, o.settled, o.dispatch_state,"
                    " o.reconcile_state FROM operations o"
                    " WHERE o.allocation_id IN (SELECT id FROM kids)"
                    " ORDER BY o.id", (handle.allocation_id,))
                ops = cur.fetchall()
            conn.commit()
    except Exception as exc:
        for key in ("dispatch_allowance", "internal_held_units"):
            out[key]["reason"] = "operations unreadable: %s" % exc
        return out
    effects = {}
    for row in ops:
        effect = str((row["payload"] or {}).get("effect") or "unlabelled")
        effects[effect] = effects.get(effect, 0) + 1
    unsettled = [row for row in ops if not row["settled"]]
    out["dispatch_allowance"] = {
        "status": "REPORTED",
        "allocation_id": handle.allocation_id,
        "operations": len(ops),
        "by_effect": dict(sorted(effects.items())),
        "settled": len(ops) - len(unsettled),
        "unsettled": len(unsettled),
        "unsettled_operation_ids": [row["id"] for row in unsettled],
        "dispatch_states": _tally(row["dispatch_state"] for row in ops),
        "reconcile_states": _tally(row["reconcile_state"] for row in ops),
        "uncertain": len(unsettled),
        "uncertain_note": "an operation that was dispatched and is not"
                          " settled may have spent a provider call whose"
                          " response was lost; its cost is uncertain, not"
                          " zero",
    }
    try:
        out["internal_held_units"] = {
            "status": "REPORTED",
            "free_units": int(store.allocation_free(
                dsn, handle.allocation_id)),
            "note": "free = authorized minus consumed minus children's"
                    " authorization",
        }
    except Exception as exc:
        out["internal_held_units"] = {
            "status": "UNMEASURED", "reason": "%s" % exc}
    return out


def _tally(values) -> dict:
    out: dict = {}
    for value in values:
        key = str(value if value is not None else "null")
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items()))


# ---------------------------------------------------------------------------
# the artifact
# ---------------------------------------------------------------------------


def build(study_out: Path, dest: Path, *, dsn: str | None = None,
          study_root: str = "", control_arm: str = CONTROL_ARM,
          cost: dict | None = None,
          acquired_ordering: str = "I") -> dict:
    """Write the result artifact for one run, and return its summary.

    `dest` must not already exist. This never writes into an existing
    `reports/evidence/` directory: the caller names a new one, and a name
    that is already taken is a refusal rather than an overwrite.
    """
    if dest.exists():
        raise FileExistsError(
            "refusing to write a result artifact over %s" % dest)
    records = json.loads(
        (study_out / "use_records.json").read_text(encoding="utf-8"))
    control, acquired = split_arms(records, control_arm=control_arm)
    orderings = split_acquired_orderings(acquired)
    # The gate and the utility both pair the control against one acquired
    # ordering. The use loop runs both, so pairing against all of them
    # would count every task twice and halve the mean delta by counting
    # each observation twice. I is the first ordering; the choice is named
    # in the summary rather than left implicit.
    compared = orderings.get(acquired_ordering, [])
    if not compared:
        compared = acquired
    paired = per_task(arm_rows(control), arm_rows(compared))
    distinct = gate_control_distinct(control, compared)
    experience = gate_experience(control, arm_name="control")
    utility_verdict = utility(paired)

    accounting = {}
    if (study_out / "accounting.json").exists():
        accounting = json.loads(
            (study_out / "accounting.json").read_text(encoding="utf-8"))
    freeze = {}
    if (study_out / "freeze.json").exists():
        freeze = json.loads(
            (study_out / "freeze.json").read_text(encoding="utf-8"))
    if cost is None and (study_out / "run_cost.json").exists():
        # The run harness reads the four currencies while the store still
        # exists and writes them here. After the drop there is nothing left
        # to measure them from, so a build without this reports every
        # currency UNMEASURED rather than guessing.
        cost = json.loads(
            (study_out / "run_cost.json").read_text(encoding="utf-8"))
    if cost is None:
        cost = cost_currencies(dsn=None, study_root=study_root)

    dest.mkdir(parents=True)
    _write(dest / "control_distinct.json", distinct)
    _write(dest / "experience_varies.json", experience)
    _write(dest / "arms.json", {
        "control": arm_rows(control),
        "acquired": arm_rows(acquired),
        "acquired_by_ordering": {name: arm_rows(rows)
                                 for name, rows in orderings.items()},
        "compared_ordering": acquired_ordering,
        "per_task": paired,
    })
    _write(dest / "cost.json", cost)
    _write(dest / "study_accounting.json",
           {"accounting": accounting, "freeze": freeze})
    summary = {
        "control_records": len(control),
        "acquired_records": len(acquired),
        "acquired_orderings": sorted(orderings),
        "compared_ordering": acquired_ordering,
        "paired_tasks": len(paired),
        "control_distinct": distinct.get("distinct"),
        "control_distinct_refusal": distinct.get("refusal", ""),
        "experience_varies": experience.get("varies"),
        "experience_refusal": experience.get("refusal", ""),
        "utility": utility_verdict["value"],
        "mean_acquired_minus_control":
            utility_verdict["mean_acquired_minus_control"],
        "executed_policy_ids": {
            "control": sorted({r["executed_policy_id"] for r in
                               arm_rows(control)}),
            "acquired": sorted({r["executed_policy_id"] for r in
                                arm_rows(acquired)}),
        },
        "cost": {name: body.get("status", "REPORTED")
                 for name, body in cost.items()},
    }
    _write(dest / "summary.json", summary)
    (dest / "summary.md").write_text(
        _markdown(summary, distinct, experience, paired, cost),
        encoding="utf-8")
    return summary


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, indent=1,
                               default=str) + "\n", encoding="utf-8")


def _markdown(summary: dict, distinct: dict, experience: dict,
              paired: list, cost: dict) -> str:
    lines = [
        "# E1 with a control arm in the study",
        "",
        "A control arm is in the study and it ran. This is what the two arms"
        " executed and what the difference between them was.",
        "",
        "## The gate",
        "",
        "`control_distinct`: **%s**" % summary["control_distinct"],
        "",
    ]
    if distinct.get("refusal"):
        lines += ["> %s" % distinct["refusal"], ""]
    verdict = distinct.get("verdict") or {}
    if verdict:
        lines += [
            "paired tasks %d, unpaired %d, same strategy %d, same executed"
            " policy %d, same candidate %d, unnamed %d, differing budget %d"
            % (len(verdict.get("paired_tasks") or []),
               len(verdict.get("unpaired_tasks") or []),
               len(verdict.get("same_strategy") or []),
               len(verdict.get("same_executed_policy") or []),
               len(verdict.get("same_candidate") or []),
               len(verdict.get("unnamed_executed_policy") or []),
               len(verdict.get("differing_budget") or [])),
            "",
        ]
    lines += [
        "`experience_varies`: **%s**" % summary["experience_varies"],
        "",
    ]
    if experience.get("refusal"):
        lines += ["> %s" % experience["refusal"], ""]
    body = experience.get("verdict") or {}
    if body:
        lines += ["%d observations, %d distinct verdict(s) %s, methods named"
                  " %s." % (body.get("observations", 0),
                            body.get("distinct_verdicts", 0),
                            body.get("verdicts"),
                            body.get("methods_named")), ""]
    lines += [
        "## Utility",
        "",
        "Compared against the acquired ordering %r. The use loop runs %s,"
        " so pairing against both would count every task twice."
        % (summary["compared_ordering"],
           " and ".join(summary["acquired_orderings"])),
        "",
        "**%s** over %d paired tasks, mean acquired-minus-control"
        " normalized reduction %s."
        % (summary["utility"], summary["paired_tasks"],
           summary["mean_acquired_minus_control"]),
        "",
        "A tie is a result. It is reported here as a tie, with the numbers"
        " that produced it, and not as a failure.",
        "",
        "| task | control ran | acquired ran | control size | acquired size |"
        " same bytes | delta |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in paired:
        delta = row["acquired_reduction"] - row["control_reduction"]
        lines.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            row["task_id"], row["control_executed"],
            row["acquired_executed"], row["control_size"],
            row["acquired_size"],
            "yes" if row["candidate_digest_equal"] else "no",
            round(delta, 4) if delta is not None else "n/a"))
    lines += [
        "",
        "## Cost, in four separate currencies",
        "",
    ]
    for name in ("dispatch_allowance", "reservation_allowance",
                 "provider_billing", "internal_held_units"):
        body = cost.get(name) or {}
        lines.append("- **%s** %s" % (name, body.get("status", "REPORTED")))
        for key in ("operations", "free_units", "study_units_authorized",
                    "reason", "uncertain_note", "unsettled"):
            if key in body and body[key] not in (None, 0, ""):
                lines.append("  - %s: %s" % (key, body[key]))
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(prog="control-arm-result")
    parser.add_argument("--study-out", required=True)
    parser.add_argument("--dest", required=True)
    parser.add_argument("--dsn", default="")
    parser.add_argument("--study-root", default="")
    args = parser.parse_args()
    print(json.dumps(build(Path(args.study_out), Path(args.dest),
                           dsn=args.dsn or None,
                           study_root=args.study_root),
                     sort_keys=True, indent=2))
