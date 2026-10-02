"""Bounded review at 7941ab4; no database, provider or untrusted-code effects."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from experiments.ad01 import agenda_policy, learner, packet, records, trajectory
from scripts import inv01_study as study


def main():
    cli = subprocess.run([sys.executable, str(ROOT / "scripts/inv01_study.py"),
                          "--model", "review-live-model"], capture_output=True, text=True)
    assert cli.returncode == 2 and "unrecognized arguments" in cli.stderr

    sw, gr = "ad01-w0-dev-sw-00", "ad01-w0-dev-gr-00"
    observation = {"observation_id": "obs-review", "task_id": sw, "verdict": "unmeasured"}
    experience = {"observations": [observation]}
    proposal = {"basis_references": ["obs-review"], "question": "inspect graph",
                "next_action": {"kind": "diagnostic", "diagnostic": "graph", "task_id": gr},
                "requested_resources": {"queries": 1}}
    prior_failure = {"kind": "correction", "number": 1,
                     "failure": {"target": sw, "reason": "invented basis references: bogus", "attempt": 0}}
    captured = []
    def proposer(seen, asked):
        captured.append(copy.deepcopy(seen))
        return proposal
    consumer = agenda_policy.DecisionConsumer(proposer=proposer, dsn="review-read-double", cid="review-cid")
    with patch.object(agenda_policy, "_correction_rows", return_value=[prior_failure]):
        decision = consumer.decide(experience, {"objective": "review"},
                                   boundary={"world": 0, "arm": "I", "seq": 0},
                                   experience=experience, aid="review-attempt")
    assert decision["status"] == "admitted"
    assert decision["investigation"]["next_action"]["task_id"] == gr
    assert "prior_failure" not in captured[0]

    accepted = {"basis_references": ["obs-review"], "question": "inspect graph",
                "next_action": {"kind": "diagnostic", "diagnostic": "graph", "task_id": gr},
                "requested_resources": {"queries": 1}}
    diag_calls = []
    original_diag = trajectory.run_diagnostic
    def observe_diagnostic(*args, **kwargs):
        result = original_diag(*args, **kwargs)
        diag_calls.append(result["queries"])
        return result
    with patch.object(trajectory, "run_diagnostic", side_effect=observe_diagnostic):
        for _ in range(2):
            trajectory._run_boundary(
                gr, "seed-gr-greedy", {"diagnostic_queries": 16},
                {"observation_id": "obs-review", "task_id": gr, "verdict": "unmeasured"},
                charter={"objective": "review"}, boundary={"world": 0, "arm": "I", "seq": 0},
                experience={"observations": [], "remaining": {"queries": 16, "model_calls": 60}},
                state={}, accepted=copy.deepcopy(accepted))
    assert len(diag_calls) == 2 and all(n > 0 for n in diag_calls)

    cid = "review-export"
    ids = [learner._learner_op_id(cid, 0, attempt) for attempt in (0, 1)]
    ops = [{"id": op_id, "dispatch_state": "observed", "payload": {"effect": "model-inference"}}
           for op_id in ids]
    receipts = {op_id: [{"receipt_identity": "gw:" + op_id, "operation_id": op_id,
                         "outcome": "success", "content": {"text": json.dumps(proposal),
                         "usage": {"input_tokens": 5, "output_tokens": 5, "billed": False}}}]
                for op_id in ids}
    durable = {"task_id": gr, "decision": proposal, "observation": observation,
               "episode": {"kind": "diagnostic", "disposition": "inspected", "task_id": gr, "queries": 1},
               "spend": 2}
    campaign = {"campaign_id": cid, "world": 0, "arm": "I", "boundaries": [{"seq": 0, "task_id": gr}],
                "episodes": [durable["episode"]]}
    with patch.object(records, "_operations_for", return_value=ops), \
         patch.object(records, "_receipts_for", side_effect=lambda dsn, op_id: receipts[op_id]), \
         patch.object(records, "_allocation", return_value={}), \
         patch.object(trajectory, "_read_campaign", return_value=({0: durable}, {})):
        export = records.export_campaign("dbname=review-only", campaign, model="review-model",
                                         charter={"objective": "review"}, caps={"model_calls": 60})
    transition = export["transitions"][0]
    counts = records.recompute_accounting(export, [])
    assert len(export["operations"]) == 2 and transition["operations"] == ids[:1]
    assert counts["total"]["model_calls"] == 1

    with tempfile.TemporaryDirectory(prefix="inv01-review-recompute-") as directory:
        out = Path(directory)
        (out / "exports").mkdir()
        records.write_export(export, out / "exports/export-one.json")
        (out / "use_records.json").write_text("[]", encoding="utf-8")
        (out / "accounting.json").write_text(json.dumps({"total": {
            "model_calls": 1, "construction_calls": 0, "witness_queries": 999999, "use_records": 24}}), encoding="utf-8")
        recompute_rc = study.recompute_study(out, out / "recomputed.json")
        recomputed = json.loads((out / "recomputed.json").read_text())
    assert recompute_rc == 0 and recomputed["total"]["use_records"] == 0

    print(json.dumps({"reviewed_commit": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "scope": "Real CLI parse; real consumer/admission with stored-correction read double; real diagnostic twice at accepted boundary; export from controlled stored rows; actual offline recompute. No live or database qualification.",
        "live_cli": {"exit": cli.returncode, "error": cli.stderr.strip()},
        "correction_resume": {"stored_refused_target": sw, "accepted_target": gr,
                              "failure_in_prompt": "prior_failure" in captured[0], "corrections": decision["corrections"]},
        "pending_boundary_diagnostics": {"executions": len(diag_calls), "queries_each": diag_calls},
        "correction_export": {"stored_operations": ids, "exported_transition_operations": transition["operations"],
                              "recomputed_model_calls": counts["total"]["model_calls"]},
        "incomplete_use_recompute": {"exit": recompute_rc, "claimed_use_records": 24,
                                     "actual_use_records": recomputed["total"]["use_records"],
                                     "claimed_queries": 999999, "actual_queries": recomputed["total"]["witness_queries"]}}, indent=2))


if __name__ == "__main__":
    main()
