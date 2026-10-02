"""Bounded review probes: no database, network, provider or generated policy execution."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from experiments.coord02 import entry, schemas_evidence as se


def trial(arm="L"):
    return se.build_trial_record(
        freeze_id="review", panel="evaluation", task_id="c02-t03", repeat=1,
        arm=arm, source_sha="review", config_digest="review", package_digest="none",
        outcome="failure", solved=False, protected={"passed": 0, "failed": 1, "total": 1},
        failures=[{"reason": "none-selection:S-fallback"}],
        costs=entry._cell_costs("unused", None, {}), receipts=["review-operation"],
        operations=[{"operation_id": "review-operation", "kind": "episode"}])


def observe():
    costs = [entry._cell_costs("unused", None, {"steps": n, "probe_calls": 0}) for n in (0, 50)]
    with tempfile.TemporaryDirectory(prefix="ec02-review-") as scratch:
        root = Path(scratch)
        unstaged = entry.stage_record(root, trial(), None)
        with patch.object(entry.oracle, "evaluate_tree", return_value={"passed": 1, "failed": 0, "total": 1, "failures": []}):
            staged = entry.stage_record(root, trial(), {"src/app.py": "value = 1\n"})
        cell = {"panel": "evaluation", "task": "c02-t03", "repeat": 1, "arm": "L"}
        key = ("review", "evaluation", "c02-t03", 1, "L")
        freeze = {"freeze_id": "review", "package": {"kind": "none"}}
        resume = se.resume_plan(freeze=freeze, schedule_cells=[cell], evidence_by_key={key: unstaged}, pending_by_key={})
        fabricated = se.resume_plan(
            freeze={"freeze_id": "review", "package": {"digest": "policy"}},
            schedule_cells=[cell], evidence_by_key={key: {"procedure_digest": "policy", "frozen_digest": "policy", "outcome": "failure"}},
            pending_by_key={})
    seen = {}
    seed = {"allocation_id": "review-allocation", "investigation_id": "review-investigation", "snapshot_digest": "review-snapshot"}

    def run(dsn, cfg, launchers, factory):
        seen["entry"] = cfg.package["entry_bytes"]
        seen["repair"] = factory("w1", {"owned_paths": list(cfg.snapshot)}, {})
        return {"status": "stopped", "reason": "review interception", "steps": 0}

    outputs = []
    for action in ("stop", "unsupported"):
        with patch.object(entry, "seed_episode", return_value=seed), patch.object(entry, "_interpret_with_model", return_value={"proposal": {"action": action, "reason": "distinct-model-response"}, "usage": {}, "text": action}), patch.object(entry, "run_episode", side_effect=run), patch.object(entry, "_cell_receipts", return_value=["review-operation"]):
            entry.run_cell("unused", freeze={"freeze_id": "review"}, task_id="c02-t03", panel="evaluation", repeat=1, arm="A", launcher_factory=lambda _: {}, package_text="ACQUIRED-SOURCE-SENTINEL")
        outputs.append(dict(seen))
    return {
        "scope": "real Python seams; database/model/join endpoints intercepted; no live claims",
        "fixed_model_usage": [{k: c[k] for k in ("model_tokens_in", "model_tokens_out", "model_calls")} for c in costs],
        "staged_fallback": {"arm": staged["arm"], "outcome": staged["outcome"], "failures": staged["failures"]},
        "unstaged_marker_preserved": unstaged["failures"] == trial()["failures"],
        "real_record_resume": {k: len(v) for k, v in resume.items()},
        "fabricated_digest_record_resume": {k: len(v) for k, v in fabricated.items()},
        "different_A_responses_same_controller_program": outputs[0]["entry"] == outputs[1]["entry"],
        "different_A_responses_same_repair_bytes": outputs[0]["repair"] == outputs[1]["repair"],
        "repair_equals_unmodified_snapshot": outputs[0]["repair"] == entry.snapshot_files("c02-t03"),
        "gateway_factory": type(entry.gateway_factory()).__name__,
    }


if __name__ == "__main__":
    print(json.dumps(observe(), indent=2))
