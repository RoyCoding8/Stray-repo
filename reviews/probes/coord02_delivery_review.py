"""Read-only semantic probes for delivery 0b47dcf; no DB or provider access."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from experiments.coord02 import entry, experience, oracle


def policy_result(arm, task):
    with tempfile.TemporaryDirectory(prefix="coord02-review-") as area:
        root = Path(area)
        program, request, response = [root / p for p in ("policy.py", "request.json", "response.json")]
        program.write_bytes(entry.arm_policy_entry(arm, task_id=task, package_digest="retained-program"))
        request.write_text(json.dumps(dict(profile="coordination-procedure", profile_version="coordination-procedure/1", decision_id="review", package_digest="retained-program", source_digest="snapshot", plan_revision=0, phase="post-probe")))
        subprocess.run([sys.executable, str(program), str(request), str(response)], check=True, capture_output=True, timeout=10)
        return json.loads(response.read_text())["proposal"]


def main():
    task = oracle.SPLITS["development"][0]
    accessed = []
    for arm in entry.ARMS:
        with patch.object(experience.oracle, "overlay_files", side_effect=RuntimeError("protected-reference-read")):
            try:
                entry.arm_child_factory(arm, task, "retained source")("w1", {"owned_paths": []}, {})
            except RuntimeError as error:
                if str(error) != "protected-reference-read":
                    raise
                accessed.append(arm)
    before = entry._cell_costs("unused", None, {"steps": 1, "probe_calls": 0})
    after = entry._cell_costs("unused", None, {"steps": 50, "probe_calls": 4})
    packet = {"probe_observations": [{"output": "visible-observation"}], "plans": ["PLAN_SENTINEL"], "joins": ["JOIN_SENTINEL"], "actual_artifacts": ["SOURCE_SENTINEL"], "failures": ["FAILURE_SENTINEL"]}
    request = experience.construction_request(packet, experience.construction_budget(), lineage=1, attempt="init")
    prompt = experience.render_construction_prompt(request)
    executed = []
    freeze = {"freeze_id": "review", "schedule": [{"panel": "evaluation", "task": task, "repeat": 1, "arm": arm} for arm in ("L", "F", "A", "S")]}
    with patch.object(entry, "run_cell", side_effect=lambda *args, **kwargs: executed.append(kwargs["arm"])):
        entry.run_panel("unused", freeze=freeze, panel="evaluation", launcher_factory=None, repeats=(1,))
    print(json.dumps({
        "reviewed_tip": "0b47dcf",
        "external_access": "none; authored baseline subprocesses only",
        "arms_requesting_protected_reference_overlay": accessed,
        "S_and_A_same_proposal": policy_result("S", task) == policy_result("A", task),
        "costs_one_step": before,
        "costs_fifty_steps": after,
        "construction_prompt_contains_observation": "visible-observation" in prompt,
        "construction_prompt_omits": [v for v in ["PLAN_SENTINEL", "JOIN_SENTINEL", "SOURCE_SENTINEL", "FAILURE_SENTINEL"] if v not in prompt],
        "over_input_token_cap_problems": entry.check_ceilings({"model_tokens_in": 1_000_000, "model_tokens_out": 0}),
        "frozen_arm_order": [c["arm"] for c in freeze["schedule"]],
        "executed_arm_order": executed,
        "fresh_ledger_with_same_allocation_remaining": [experience.ConstructionLedger("unused", "same-allocation").remaining() for _ in range(2)],
    }, indent=2))


if __name__ == "__main__":
    main()
