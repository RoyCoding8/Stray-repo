"""Offline evidence checks and isolated boundary probes; no DB or provider calls."""

import hashlib
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from experiments.ad01 import checker, construct, trajectory, worlds

ROOT = Path(__file__).resolve().parents[2]


def prompt_probe():
    task = worlds.load_task(worlds.FROZEN_DIR, "ad01-w0-dev-sw-00")
    obs = {"observation_id": "prior", "task_id": task["task_id"],
           "verdict": "preserved", "detail": {"measurement": "first"}}
    first = construct._prompt(task, {"observations": [obs]}, {}, None)
    second = construct._prompt(worlds.load_task(worlds.FROZEN_DIR, "ad01-w0-dev-sw-01"),
                               {"observations": [{**obs, "detail": {
                                   "measurement": "second"}}]}, {}, None)
    assert first == second
    return {"changed_task_and_diagnostic_detail_change_prompt": False,
            "prompt_sha256": hashlib.sha256(first.encode()).hexdigest(),
            "prompt": first}


def boundary_probe():
    target = "ad01-w0-dev-gr-00"
    seed = {"observation_id": "seed", "task_id": target, "verdict": "unmeasured"}
    proposal = {"basis_references": ["seed"], "question": "test",
                "next_action": {"kind": "development", "task_id": target,
                                "diagnostic": "graph", "max_queries": 15},
                "requested_resources": {"queries": 15}}
    observed = {"observation_id": "new-diagnostic", "task_id": target,
                "verdict": "preserved", "detail": "DISTINGUISHING-RESULT", "queries": 10}
    captured = {}

    def capture(*args, **kwargs):
        captured.update(kwargs)
        raise construct.ConstructionFailed("probe stops before model execution")

    with patch.object(trajectory, "run_diagnostic", return_value=observed), \
            patch.object(construct, "construct_method", side_effect=capture):
        trajectory._run_boundary(
            target, "seed-gr-greedy", {"diagnostic_queries": 16}, seed,
            propose=lambda *args: proposal, charter={"objective": "test"},
            boundary={"world": 0, "arm": "I", "seq": 0},
            experience={"observations": [], "remaining": {"queries": 16, "model_calls": 60}},
            state={"dev_episodes": 0, "model_calls": 0, "construction_calls": 0},
            construction={"dsn": None, "cid": "probe", "gateway": None, "model": "none"})
    visible = [o["observation_id"] for o in captured["experience"]["observations"]]
    assert "new-diagnostic" not in visible
    assert captured["budget"]["max_queries"] == 15
    return {"kind": "isolated boundary with diagnostic and constructor doubles",
            "constructor_observations": visible, "diagnostic_queries_already_spent": 10,
            "initial_allowance": 16, "constructor_query_allowance": 15,
            "remaining_after_diagnostic_and_boundary_charge": 5}


def evidence_probe():
    directory = ROOT / "evidence-ad01/c4-live"
    traces, empty = [], []
    for file in sorted(directory.glob("*.json")):
        if not file.read_bytes().strip():
            empty.append(file.name)
            continue
        data = json.loads(file.read_text())
        traces.append({"file": file.name, "world": data["world"], "arm": data["arm"],
                       "campaign": data["campaign_id"],
                       "retained": data["accounting"]["mechanism"]["retained"],
                       "unknown_tokens": data["accounting"]["total"]["tokens"] is None,
                       "exported_operation_entries": len(data["accounting"]["operations"])})
    records = [record for file in sorted((ROOT / "evidence-ad01/c3-trajectories-merged").glob("use-*.json"))
               for record in json.loads(file.read_text())]
    checked = checker.verify_use_records(records, worlds.FROZEN_DIR)
    assert len(records) == 72 and not checked["problems"]
    fallback = trajectory.run_use({"campaign_id": "offline-empty", "members": []},
                                  0, "I", ["ad01-w0-within-sw-00"], {})
    assert fallback[0]["executed"] == "incumbent"
    acquisition = json.loads((ROOT / "evidence-live/c2-acquisition8.json").read_text())
    reasons = {str(r["lineage"]): sorted({f["reason"] for f in r["validation"]["failures"]})
               for r in acquisition["results"]}
    return {"c4_readable_traces": len(traces), "c4_empty_stubs": empty, "c4_traces": traces,
            "c3_use_records": len(records), "c3_checker": checked,
            "empty_repertoire_fallback": fallback[0]["executed"], "c2_init_failure_reasons": reasons}


if __name__ == "__main__":
    print(json.dumps({"reviewed_source": "84d20948ddbef8efea38a5728edd3fddc6b3a936",
                      "checkout": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                      "prompt": prompt_probe(), "boundary": boundary_probe(),
                      "evidence": evidence_probe()}, indent=2))
