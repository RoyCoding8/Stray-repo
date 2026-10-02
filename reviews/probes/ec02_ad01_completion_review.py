"""Bounded, offline reviewer observations; no provider or database access."""

import ast
import inspect
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from experiments.ad01 import trajectory as T
from experiments.coord02 import entry as E, schemas_evidence as S


def semantic(source):
    return ast.dump(ast.parse(source), include_attributes=False)


def main():
    task = "c02-t01"
    child = E.plan_children(task, "single")[0]
    factory = E.admitted_child_factory(task)
    a = factory("w1", {**child, "obligation": "repair normalization"}, {})
    b = factory("w1", {**child, "obligation": "repair arithmetic"}, {})
    original = E.snapshot_files(task)
    python = [p for p in a if p.endswith(".py")]
    stamp = {"changed_bytes": a != b, "python_files": len(python),
             "all_semantically_unchanged": all(
                 semantic(a[p]) == semantic(b[p]) == semantic(original[p])
                 for p in python)}
    assert stamp["changed_bytes"] and stamp["all_semantically_unchanged"]
    try:
        E.arm_child_factory("S", task, constructor_label="LIVE")
    except ValueError as exc:
        stamp["live_constructor_refusal"] = str(exc)
    else:
        raise AssertionError("LIVE constructor behavior changed; reassess")

    costs = E._cell_costs("never-connected", None, {"steps": 3, "probe_calls": 2})
    assert (costs["model_tokens_in"], costs["model_tokens_out"], costs["model_calls"]) == (100, 20, 1)
    records = [json.loads(p.read_text()) for p in
               (ROOT / "evidence-live/c2-fallback/episodes").glob("*.json")]
    evidence = {arm: {"records": len(rows),
                     "failures": sum(r["outcome"] == "failure" for r in rows),
                     "fixed_100_20_tokens": sum(r["costs"]["model_tokens"] == {"in": 100, "out": 20} for r in rows),
                     "model_calls_one": sum(r["costs"]["model_calls"] == 1 for r in rows)}
                for arm in E.ARMS if (rows := [r for r in records if r["arm"] == arm])}
    invented = {"outcome": "success", "procedure_digest": "none",
                "receipts": ["invented-not-reconciled"]}
    skip = S._resume_skippable(invented, None, None, none_selection=True)
    assert skip

    charter = {"objective": "smaller valid explanatory examples", "freeze_id": "ad01"}
    caps = {"max_boundaries": 6, "diagnostic_queries": 16}
    i = T.run_campaign(0, "I", charter, caps)
    r = T.run_campaign(0, "R", charter, caps)
    path_i = [b["task_id"] for b in i["boundaries"]]
    path_r = [b["task_id"] for b in r["boundaries"]]
    with patch.object(T, "next_decision", return_value={"action": "stop", "reason": "review intervention"}):
        stopped = T.run_campaign(0, "I", charter, caps)
    assert path_i == path_r and len(stopped["episodes"]) == len(i["episodes"]) > 0
    retained = [e["executable"] for e in i["episodes"] if e["disposition"] == "retained"]
    assert retained and all(e["authored"] for e in retained)
    with patch.object(T, "next_decision", return_value={"action": "stop"}):
        six = T.run_campaign(0, "I", charter, caps, tasks=path_i + path_i)
    assert len(six["episodes"]) == 6
    observed_inputs = []

    def learner(experience, supplied_charter):
        observed_inputs.append({"observations": experience["observations"], "charter": supplied_charter})
        proposal = T.propose_investigation(experience, supplied_charter)
        proposal["next_action"]["diagnostic"] = "software"
        return proposal

    T.run_campaign(0, "I", charter, caps, propose=learner)
    assert all(len(x["observations"]) == 1 and x["observations"][0]["verdict"] == "unmeasured"
               and x["charter"] == {} for x in observed_inputs)
    persisted = {n: {"row_id": f"row-{n}", "task_id": b["task_id"],
                     "observation_id": b["observation_id"], "spend": b["spend"],
                     "episode": {"disposition": e["disposition"], "queries": e["queries"]}}
                 for n, (b, e) in enumerate(zip(i["boundaries"], i["episodes"]))}
    with patch.object(T, "ensure_campaign"), patch.object(T, "_read_campaign", return_value=(persisted, {})):
        resumed = T.run_campaign(0, "I", charter, caps, dsn="never-connected")
    assert not any(e.get("executable") for e in resumed["episodes"])
    acquisition = json.loads((ROOT / "evidence-live/c2-acquisition6.json").read_text())
    return {"reviewed_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "bounds": "Offline source/fixture probes and committed JSON; no live calls or database reconciliation. Resume uses the exact persisted episode shape with a mocked read, not a process-kill proof.",
            "child_semantics": stamp, "direct_costs_without_database": costs,
            "committed_fallback": evidence, "unreconciled_invented_receipt_skips": skip,
            "ad01": {"default_I_tasks": path_i, "default_R_tasks": path_r,
                     "forced_stop_still_runs_episodes": len(stopped["episodes"]),
                     "six_boundaries_run_six_episodes": len(six["episodes"]),
                     "retained_all_authored": retained,
                     "learner_inputs": observed_inputs,
                     "persisted_shape_loses_executable_on_resume": True},
            "acquisition": {"accounting": acquisition["accounting"],
                            "stages": [{"lineage": x["lineage"], "stage": x["stage"],
                                        "profile_reason": x["validation"]["profile_reason"]}
                                       for x in acquisition["results"]]},
            "source_integration": {"entry_calls_store_reconciliation": "reconcile_campaign_union_from_store" in inspect.getsource(E),
                                   "public_panel_calls_resume_plan": "resume_plan" in inspect.getsource(E.run_panel)}}


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
