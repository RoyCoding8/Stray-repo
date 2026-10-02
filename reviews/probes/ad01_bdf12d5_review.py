"""Offline review probes using trusted controls; no provider or DB access."""

import inspect
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from experiments.ad01 import benefit, checker, trajectory as T, worlds
from experiments.coord02 import controller as C, entry as E


def main():
    calls = []

    def capture(dsn, **kw):
        calls.append({k: kw[k] for k in ("operation_id", "node", "child")})
        return {}

    with patch.object(E, "dispatch_admitted_child", side_effect=capture):
        factory = E.run_child_factory("unused", task_id="c02-t01", gateway=None,
                                     model="review-double", allocation_id="unused",
                                     operation_id="one-cell")
        for node, obligation in (("w1", "first"), ("w2", "second"), ("w1", "rework")):
            factory(node, {"obligation": obligation, "owned_paths": []}, {})
    assert len({r["operation_id"] for r in calls}) == 1
    child = {"node_id": "w1", "obligation": "repair", "owned_paths": [],
             "input_bindings": {}, "output_contract": {}}
    rendered = C.render_child_obligation(child, [{"interface": "probe",
                                                 "output": {"witness": "DISTINCT-RESULT"}}])
    assert "DISTINCT-RESULT" not in json.dumps(rendered)

    trusted_source = ("import os\n"
                      "def review_method(task, oracle, max_queries=16):\n"
                      "    return {'candidate': task, 'queries': 0, 'pid': os.getpid()}\n")
    member = {"capability_id": "review-own-pid-control", "method_source": trusted_source,
              "entry": "review_method", "params": {"max_queries": 1}}
    task = worlds.load_task(worlds.FROZEN_DIR, "ad01-w0-dev-sw-00")
    own = T._run_member(member, task)
    assert own["pid"] == os.getpid()

    charter = {"objective": "smaller valid explanatory examples", "freeze_id": "ad01"}
    caps = {"max_boundaries": 2, "diagnostic_queries": 16}
    seen = []

    def propose(experience, asked):
        seen.append({"experience": experience, "charter": asked})
        seed = experience["observations"][0]
        return {"basis_references": [seed["observation_id"]], "question": "inspect",
                "next_action": {"kind": "development", "diagnostic": "software",
                                "task_id": seed["task_id"]}, "requested_resources": {}}

    campaign = T.run_campaign(0, "I", charter, caps, propose=propose)
    assert all(len(x["experience"]["observations"]) == 1 and
               x["experience"]["observations"][0]["verdict"] == "unmeasured" for x in seen)

    def future(experience, asked):
        result = propose(experience, asked)
        result["next_action"]["task_id"] = "ad01-w0-within-sw-00"
        return result

    future_run = T.run_campaign(0, "I", charter, {**caps, "max_boundaries": 1}, propose=future)
    assert future_run["episodes"][0]["task_id"] == "ad01-w0-within-sw-00"

    committed = ROOT / "evidence-ad01/c3-trajectories"
    records = [r for p in sorted(committed.glob("use-*.json")) for r in json.loads(p.read_text())]
    members = [m for p in sorted(committed.glob("repertoire-*.json"))
               for m in json.loads(p.read_text())["members"]]
    verification = checker.verify_use_records(records, worlds.FROZEN_DIR)
    assert len(records) == 72 and not verification["problems"]
    assert len(members) == 15 and all(m["authored"] and "method_source" not in m for m in members)
    with tempfile.TemporaryDirectory(prefix="ad01-bdf-review-") as scratch:
        root = Path(scratch).resolve()
        assert root.parent == Path(tempfile.gettempdir()).resolve()
        output = root / "qualification"
        proc = subprocess.run([sys.executable, "-m", "experiments.ad01.run_c3_qualification", str(output)],
                              cwd=ROOT, text=True, capture_output=True, timeout=120)
        assert proc.returncode == 0, proc.stderr
        same = {p.name: json.loads(p.read_text()) == json.loads((output / p.name).read_text())
                for p in committed.glob("*.json")}
        assert len(same) == 19 and all(same.values())

    return {"reviewed_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "bounds": "Trusted offline canary and direct-boundary probes, committed evidence checks, fresh qualification subprocess. No provider calls, DB access, or untrusted program execution. Factory identity probe captures arguments rather than asserting a real-DB outcome.",
            "child_call_identities": calls, "diagnostic_renderer": rendered,
            "trusted_method_executes_in_host_pid": own["pid"] == os.getpid(),
            "learner_packets": seen[:2],
            "protected_target_accepted_during_development": future_run["episodes"][0]["task_id"],
            "committed_qualification": {"use_records": len(records), "retained_members": len(members),
                                        "all_members_authored": True, "checker": verification,
                                        "benefit_from_use_records_only": benefit.evaluate(records),
                                        "fresh_subprocess_jsons_equal": same},
            "public_accounting_still_constant": E._cell_costs("unused", None, {})["model_tokens_in"] == 100,
            "cost_helper_connected_to_entry": "costs_for_operations(" in inspect.getsource(E),
            "ad01_cli_has_provider_path": any(s in (ROOT / "experiments/ad01/cli.py").read_text()
                                              for s in ("gateway", "HttpGateway", "propose=")),
            "development_episode_still_seed_only": "seeds.SEED_CAPABILITIES" in inspect.getsource(T.dev_episode)}


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
