"""Offline review probes at 44f1f7c; no provider or database effects."""

import ast
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from experiments.ad01 import construct, learner, method_exec, packet, trajectory, worlds
from settlement import broker, store


def main():
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    sites = []
    for folder in ("src", "experiments", "scripts", "tests"):
        for path in (ROOT / folder).rglob("*.py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            except (SyntaxError, UnicodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    name = getattr(node.func, "id", getattr(node.func, "attr", ""))
                    if name == "run_boundary":
                        sites.append(f"{path.relative_to(ROOT).as_posix()}:{node.lineno}")
    assert sites and all(site.startswith("tests/") for site in sites), sites

    seeded = []
    with patch.object(store, "seed_allocation", side_effect=lambda dsn, cmd: seeded.append({"dsn": dsn, **cmd.payload})):
        for dsn in ("review-double-db-a", "review-double-db-b"):
            construct._construction_allocation(dsn, "same-study-b0", {"max_output_tokens": 2048})
    assert [row["authorized"] for row in seeded] == [16384, 16384]
    assert all("parent_id" not in row for row in seeded)

    seen = []
    def reject_then_stop(experience, charter):
        seen.append(copy.deepcopy(experience))
        if len(seen) == 1:
            raise learner.LearnerRefused("review-specific-invalid-proposal")
        return {"basis_references": [experience["observations"][-1]["observation_id"]],
                "question": "stop", "next_action": {"kind": "stop"},
                "requested_resources": {}}
    campaign = trajectory.run_campaign(
        0, "I", {"objective": "review"}, {"max_boundaries": 2, "diagnostic_queries": 16},
        tasks=["ad01-w0-dev-sw-00", "ad01-w0-dev-sw-01"], propose=reject_then_stop)
    assert [entry["boundary"]["seq"] for entry in seen] == [0, 1]
    assert "review-specific-invalid-proposal" not in json.dumps(seen[1])

    task = worlds.load_task(worlds.FROZEN_DIR, "ad01-w0-dev-sw-00")
    prompt = construct._prompt(task, {"observations": []}, {"max_output_tokens": 2048}, None)
    results = {}
    with tempfile.TemporaryDirectory(prefix="inv01-review-abi-") as directory:
        work = Path(directory)
        (work / "task.json").write_text(json.dumps({"task": task, "max_queries": 0}), encoding="utf-8")
        driver = method_exec._DRIVER % ("method", 3)
        for label, expression in (("bare_candidate", "task"), ("wrapped_candidate", "{'candidate': task}")):
            text = f"def method(task, oracle, max_queries=16):\n    return {expression}\n"
            method_exec.verify_member({"method_source": text, "entry": "method"})
            (work / "member.py").write_text(text, encoding="utf-8")
            run = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", driver,
                                  str(work), "unused-no-oracle", str(ROOT)],
                                 capture_output=True, text=True, timeout=20)
            assert run.returncode == 0, run.stderr
            results[label] = json.loads(run.stdout)
    assert results["bare_candidate"]["status"] == "error", results
    assert results["wrapped_candidate"]["status"] == "ok", results

    large = construct._prompt(task, {"observations": [{"detail": "x" * 12000}]},
                              {"max_output_tokens": 2048}, None)
    exposure = broker.exposure_schedule(broker.MODEL_INFERENCE,
        {"model": "review-not-called", "messages": [{"role": "user", "content": large}],
         "max_output_tokens": 2048, "deadline_ms": 300000}, 0)
    assert len(large) > construct.PROMPT_BUDGET_CHARS
    output = {"reviewed_commit": source,
              "boundaries": "Static analysis, allocation-command spy, public callback diagnostic, trusted fixture subprocess; no DB or live calls.",
              "shared_loop_call_sites": sites,
              "construction_seed_commands": seeded,
              "rejected_proposal": {"next_boundary": seen[1]["boundary"],
                                    "failure_in_next_packet": False,
                                    "episodes": campaign["episodes"]},
              "method_result_contract": {"declared_entry_rules": method_exec.entry_contract(),
                                         "prompt_chars": len(prompt),
                                         "bare_candidate": results["bare_candidate"],
                                         "wrapped_candidate_status": results["wrapped_candidate"]["status"]},
              "prompt_bound": {"declared_chars": construct.PROMPT_BUDGET_CHARS,
                               "observed_chars": len(large), "scheduled_exposure": exposure}}
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
