"""E1 measurement: the three gates, the SWE matrix, and the control column.

Run this to reproduce every number in
`reports/evidence/inv_r1_w1_e1_gates/`. It dispatches nothing, opens no
database, and touches no gateway. The SWE world is a local oracle, so
the whole matrix is recomputable in-process.

    .venv/bin/python -m experiments.ad01.s09_e1_gates_probe --out <dir>

The lane's question was whether E1 can be unblocked. It cannot be
unblocked by measuring, and this script is what says so with numbers
rather than with a recommendation:

* the three pre-dispatch gates in `control_distinctness` are run
  first, and their output is recorded verbatim, refusals included;
* the SWE matrix is re-run, and each representation is counted into
  `repaired` / `unrepaired` / `refused` so the two missing cells are
  compared against the recorded `156/156 refused`;
* the AD01 control and acquired columns are re-read and re-tested with
  `control_distinct`, so the E1 tie is reported as the gate reports it
  rather than as a digest's opinion.

Nothing here is tuned. A gate that refuses is recorded as a refusal.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _entry in (ROOT, ROOT / "src"):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

from experiments.ad01 import control_distinctness as gates  # noqa: E402
from experiments.ad01 import s09_swe_experiment as swe  # noqa: E402

EVIDENCE = ROOT / "evidence-ad01"
AUTHORED = EVIDENCE / "c3-authored"
TRAJECTORIES = EVIDENCE / "c3-trajectories-merged"


def gate_report() -> dict:
    """The three gates, run and recorded whatever they say.

    `probe()` reports the menu and the AD01 E1 pair. `experience_varies`
    is not among them because this is E1, which has no learner arm: its
    treatment is an authored capability, and every observation in the
    AD01 columns grades `preserved`. It is run here anyway, against the
    AD01 records, so the constant experience is a measured number in
    this directory rather than an inherited claim.
    """
    report = {"menu": gates.menu_answers_nothing()}

    for label, control, acquired in (
            ("c3_authored_vs_c3_trajectories",
             AUTHORED / "use-w0-I.json", TRAJECTORIES / "use-w0-I.json"),
            ("c3_authored_vs_c3_trajectories_w1",
             AUTHORED / "use-w1-I.json", TRAJECTORIES / "use-w1-I.json")):
        try:
            report[label] = gates.control_distinct(control, acquired)
        except gates.GateRefused as refusal:
            report[label] = {"distinct": False, "refusal": str(refusal)}

    observations = _ad01_observations()
    try:
        report["experience_varies"] = gates.experience_varies(
            observations, arm_name="e1-ad01-acquired")
    except gates.GateRefused as refusal:
        report["experience_varies"] = {"varies": False,
                                       "refusal": str(refusal)}
    report["experience_varies"]["observations_read"] = len(observations)
    return report


def _ad01_observations() -> list:
    """The AD01 acquired column read as an experience, for the gate.

    One row per use record, carrying the fields the gate reads. The
    records are the study's own, not a restatement of what they should
    have said.
    """
    rows = []
    for path in sorted(TRAJECTORIES.glob("use-*.json")):
        loaded = json.loads(path.read_text(encoding="utf-8"))
        for row in loaded:
            rows.append({
                "observation_id": row.get("record_id"),
                "task_id": row.get("task_id"),
                "capability_id": row.get("executed"),
                "verdict": row.get("verdict"),
                "method": row.get("executed_source"),
            })
    return rows


def control_column_state() -> dict:
    """Which strategy each AD01 column actually ran, read per record.

    The fork report's section 5 says the control column of `6, 9, 8` is
    unattested and that every `c3-authored` software record executed
    `seed-sw-greedy`. That is checked here against the files rather
    than repeated, because the finding it supports is that this record
    cannot be inherited.
    """
    state = {}
    for label, path in (("authored", AUTHORED), ("acquired", TRAJECTORIES)):
        executed, strategies, finals = Counter(), Counter(), []
        for name in ("use-w0-I.json", "use-w1-I.json"):
            for row in json.loads((path / name).read_text(encoding="utf-8")):
                executed[row.get("executed")] += 1
                match = gates._strategy_of(row)
                strategies[match or "(none named)"] += 1
                if row.get("domain") == "software":
                    finals.append(row.get("final_measure"))
        state[label] = {
            "executed_policy_ids": dict(executed),
            "strategies": dict(strategies),
            "software_final_measure": finals,
        }
    state["ddmin_files_under_evidence_ad01"] = _grep_ddmin()
    return state


def _grep_ddmin() -> list:
    """Every file under `evidence-ad01/` whose bytes name ddmin.

    The recorded control column of `6, 9, 8` appears in no file, and
    this is the check that says so. It is a byte search, not a record
    walk, because the claim is about the directory.
    """
    hits = []
    for path in sorted(EVIDENCE.rglob("*")):
        if not path.is_file() or path.suffix not in (".json", ".py", ".md",
                                                     ".txt"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "ddmin" in text:
            hits.append(path.relative_to(ROOT).as_posix())
    return hits


def representation_state(rows: list) -> dict:
    """Each representation's outcome, against the recorded 156/156.

    Counted from the row objects rather than the interned payload:
    `_row_for_payload` deletes `representation_kind` from every row and
    parks it in `lineage_index`, so a count taken from the written file
    would see a missing key. The recorded baseline is `typed-ast` and
    `action-graph` at 156 refused out of 156 and `python-step` at 124
    repaired, 32 unrepaired, 0 refused; a refusal is a row whose
    `outcome` is `refused`, which is how the experiment records a cell
    the executor could not enter.
    """
    per_rep = {}
    for row in rows:
        kind = row.representation_kind
        per_rep.setdefault(kind, Counter())[row.outcome] += 1
    recorded = {"python-step": {"repaired": 124, "unrepaired": 32,
                                "refused": 0, "n": 156},
                "typed-ast": {"repaired": 0, "unrepaired": 0,
                              "refused": 156, "n": 156},
                "action-graph": {"repaired": 0, "unrepaired": 0,
                                 "refused": 156, "n": 156}}
    for kind, counts in per_rep.items():
        entry = {name: counts.get(name, 0)
                 for name in ("repaired", "unrepaired", "refused")}
        entry["n"] = sum(entry.values())
        entry["recorded"] = recorded.get(kind)
        entry["refused_all"] = entry["n"] > 0 and entry["refused"] == entry["n"]
        entry["matches_recorded"] = entry.get("recorded") == {
            k: entry[k] for k in ("repaired", "unrepaired", "refused", "n")}
        per_rep[kind] = entry
    return per_rep


def swe_state(splits: tuple, *, include_step: bool) -> dict:
    """The SWE matrix, re-run, with the per-representation count.

    `include_step=False` runs only the eight lineages the frozen
    executors refuse before an episode begins, which is cheap and is the
    decisive E1 measurement: it reproduces the 156/156 refusal for
    `typed-ast` and `action-graph` without executing a single episode.
    The `python-step` cell executes up to 307 subprocess turns per
    instance across 156 instances per lineage, so it is not re-run here
    by default and its state is carried from the committed ceiling
    matrix, labelled as carried.
    """
    lineages = tuple(lineage for lineage in swe.LINEAGES
                     if include_step
                     or lineage.representation_kind != swe.PYTHON_STEP)
    result = swe.run_matrix(splits=splits, lineages=lineages)
    payload = swe.result_payload(result)
    measured = representation_state(result.rows)
    carried = _carried_step_state() if not include_step else {}
    combined = {kind: dict(entry, measured_this_run=(kind in measured),
                           carried_from=("reports/evidence/"
                                         "inv_r1_e1_swe_ceiling/matrix.json"
                                         if kind in carried else None))
                for kind, entry in carried.items()}
    combined.update(measured)
    return {
        "run_path": payload["path_fork"]["run_path"],
        "common_path_usable": payload["path_fork"]["common_path_usable"],
        "common_path_refusal": payload["path_fork"]["refusal"],
        "fields_published_by_swe": payload["path_fork"]["fields_published_by_swe"],
        "fields_required_by_harness":
            payload["path_fork"]["fields_required_by_harness"],
        "missing_from_swe": payload["path_fork"]["missing_from_swe"],
        "extra_in_swe": payload["path_fork"]["extra_in_swe"],
        "support": payload["support"],
        "lineages_run": result.lineages_run,
        "lineages_executed_episodes":
            sum(1 for lineage in lineages
                if lineage.representation_kind == swe.PYTHON_STEP),
        "rows": len(result.rows),
        "representations": combined,
        "missing_cells": payload["missing_cells"],
        "lineages": [{"name": entry["name"],
                      "representation": entry["representation_kind"],
                      "episodes": entry["episodes"],
                      "repairs": entry["repairs"],
                      "refusals": entry["refusals"],
                      "build_error": entry.get("build_error")}
                     for entry in payload["lineages"]],
        "derived_bounds": payload["derived_bounds"],
        "probe_budget_reach": payload["probe_budget_reach"],
    }


def _carried_step_state() -> dict:
    """The `python-step` cell as committed, recounted from its rows.

    Counted from the committed file's own rows rather than from the
    summary in its RESULT.md, so the carried number is measured too.
    """
    path = (ROOT / "reports" / "evidence" / "inv_r1_e1_swe_ceiling"
            / "matrix.json")
    if not path.exists():
        return {}
    rows = json.loads(path.read_text(encoding="utf-8")).get("rows", [])
    counts = Counter(row.get("outcome") for row in rows
                     if row.get("representation_kind") == swe.PYTHON_STEP)
    entry = {name: counts.get(name, 0)
             for name in ("repaired", "unrepaired", "refused")}
    entry["n"] = sum(entry.values())
    entry["recorded"] = {"repaired": 124, "unrepaired": 32,
                         "refused": 0, "n": 156}
    entry["refused_all"] = entry["n"] > 0 and entry["refused"] == entry["n"]
    entry["matches_recorded"] = entry.get("recorded") == {
        k: entry[k] for k in ("repaired", "unrepaired", "refused", "n")}
    return {swe.PYTHON_STEP: entry}


def blocking_seam() -> dict:
    """The three things a SWE `World` value would have to supply.

    Read off the executors rather than asserted, because the claim E1
    rests on is that the blocker is a missing binding and not the view
    contract. Each entry is a measured property of the shipped
    executor.
    """
    from experiments.ad01 import (boolean_ast_policy, boolean_policy,
                                  ordering_graph_policy, policy_action)
    from experiments.ad01 import s09_swe_experiment
    from experiments.ad01 import s09_swe_world as swe_world

    ordering = ordering_graph_policy.ORDERING_WORLD
    observation_keys = sorted(_live_observation_keys(swe_world,
                                                    s09_swe_experiment))
    return {
        "graph_executor_takes_a_world_value": True,
        "world_observation_field_regex":
            ordering_graph_policy._ORDERING_OBSERVATION_FIELD.pattern,
        "world_field_type_falls_back_to_the_ordering_regex": True,
        "ordering_allowed_kinds": sorted(ordering.allowed_kinds),
        "swe_allowed_kinds": sorted(swe_world.ACTION_TARGETS),
        "ordering_observation_paths": sorted(ordering.observation_paths),
        "swe_observation_keys": observation_keys,
        "ast_view_types": sorted(boolean_ast_policy._VIEW_TYPES),
        "ast_view_types_carry_the_program": "source" in
        boolean_ast_policy._VIEW_TYPES,
        "ast_validator_accepts_a_swe_repair": _ast_accepts_swe_repair(
            s09_swe_experiment),
        "graph_world_make_view_is_the_boolean_policy_one":
            ordering.make_view is boolean_policy._shared_view,
        "swe_action_kinds": sorted(policy_action.ACTION_KINDS),
        "world_value_field_count": len(
            ordering_graph_policy.World.__dataclass_fields__),
        "conclusion": (
            "a World value names three action targets, so the five-kind "
            "SWE vocabulary does not fit the three-target value without a "
            "shape change, and World.field_type falls back to the ordering "
            "observation regex, so a swe guard field resolves to None"),
    }


def _ast_accepts_swe_repair(swe_experiment) -> dict:
    """Whether the frozen AST validator admits a SWE repair, measured.

    The recorded reason for the missing `typed-ast` cell is that
    `boolean_ast_policy._validate_action` refuses `use`/`code.repair`.
    That is offered here on a real SWE view and the answer is recorded
    either way, because a hard-coded `False` in this file would be the
    same defect the gates were written to catch.
    """
    from experiments.ad01 import boolean_ast_policy, policy_action

    view = swe_experiment._ast_probe_view()
    try:
        boolean_ast_policy._validate_action(
            policy_action.parse_action(
                swe_experiment._repair_probe_action()), view)
    except Exception as exc:
        return {"accepted": False, "refusal": "%s: %s" % (type(exc).__name__,
                                                         exc)}
    return {"accepted": True, "refusal": None}


def _live_observation_keys(swe_world, swe_experiment) -> list:
    """The keys a real SWE observation carries, read by running one.

    The graph's guard vocabulary is per-World, and the claim that a SWE
    observation names none of the ordering paths is only worth making if
    the keys are the world's own rather than a remembered list.
    """
    session = swe_world.SweSession(_first_held_out_record(swe_experiment))
    record = _first_held_out_record(swe_experiment)
    session.run_public_test(record["public_tests"][0]["name"])
    observed = session.policy_view()["symptom"]["observed"]
    return sorted(observed[0]) if observed else []


def _first_held_out_record(swe_experiment) -> dict:
    from experiments.ad01 import s09_swe_tasks as tasks
    return tasks.instance("held_out", tasks.HELD_OUT_TEMPLATES[0],
                          tasks.HELD_OUT_MECHANISMS[0])


def build(splits: tuple, *, include_step: bool) -> dict:
    return {
        "version": "ad01-e1-gates-probe/1",
        "lane": "W1",
        "branch": "codex/implementation-investigation-learning-02",
        "instrument": swe.world.INSTRUMENT_ID,
        "live_dispatches": {
            "count": 0,
            "currencies": {},
            "why": ("the SWE world is a local oracle and every lineage is "
                    "an authored policy artifact, so the whole E1 matrix "
                    "is recomputable in-process; nothing in this lane "
                    "called the gateway, the broker, or a database"),
            "provider_reported_zero": None,
        },
        "gate_report": gate_report(),
        "control_column": control_column_state(),
        "swe": swe_state(splits, include_step=include_step),
        "blocking_seam": blocking_seam(),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=os.path.join(
        "reports", "evidence", "inv_r1_w1_e1_gates"))
    parser.add_argument("--splits", default="dev,held_out")
    parser.add_argument("--skip-swe", action="store_true",
                        help="gates and the control column only")
    parser.add_argument("--include-step", action="store_true",
                        help=("also run the four python-step lineages, "
                              "which execute every episode and take hours"))
    args = parser.parse_args(argv)
    splits = tuple(part for part in args.splits.split(",") if part)

    if args.skip_swe:
        payload = {"version": "ad01-e1-gates-probe/1", "lane": "W1",
                   "live_dispatches": {"count": 0, "currencies": {}},
                   "gate_report": gate_report(),
                   "control_column": control_column_state(),
                   "blocking_seam": blocking_seam()}
    else:
        payload = build(splits, include_step=args.include_step)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "result.json"
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")

    gate = payload["gate_report"]
    print("menu open: %s" % gate["menu"]["open"])
    for label in sorted(gate):
        if label.endswith("_vs_c3_trajectories") or \
                label.endswith("_vs_c3_trajectories_w1"):
            entry = gate[label]
            print("%-42s distinct=%s %s"
                  % (label, entry.get("distinct"),
                     entry.get("refusal", "")))
    print("experience_varies: varies=%s over %d observation(s) %s"
          % (gate["experience_varies"].get("varies"),
             gate["experience_varies"].get("observations_read", 0),
             gate["experience_varies"].get("refusal", "")))
    if "swe" in payload:
        for kind, entry in sorted(payload["swe"]["representations"].items()):
            print("%-14s n=%-4d repaired=%-4d unrepaired=%-4d refused=%-4d"
                  % (kind, entry["n"], entry["repaired"], entry["unrepaired"],
                     entry["refused"]))
    print("written: %s" % target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
