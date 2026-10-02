import copy
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from experiments.agenda01 import checker, replay, runner
from settlement.common import ResultCode


class DecisionBackend:
    traj = "review-idle"

    def __init__(self):
        self.saved = None

    def setup(self, budgets):
        pass

    def cursor(self):
        return {"rotation": 0, "epoch": 0, "dep_versions": {}}

    def explore_free(self):
        return 64

    def idle(self, tick, policy, reason):
        return SimpleNamespace(code=ResultCode.APPLIED, data={"dec_op": "paid-decision"})

    def save_state(self, refused, admitted_fx, tick, progress):
        self.saved = {"next_tick": tick, **copy.deepcopy(progress)}


def main():
    package = Path(__file__).resolve().parents[2] / "experiments/agenda01"
    manifest = json.loads((package / "manifest_v2.json").read_text())
    digest = (package / "manifest_v2.sha256").read_text().strip()
    files = sorted((package / "results_v2").glob("w*.json"))
    traces = [json.loads(p.read_text()) for p in files]
    worlds = {w["world_id"]: w for w in manifest["worlds"]}
    original = checker.check_dir(package / "results_v2", manifest, digest, manifest["budgets"], expect_full=True)
    mutations = {}
    for name, edit in {
        "marked_incomplete": lambda t: t.update(complete=False),
        "missing_decision_references": lambda t: [x.update(dec_op=None) for x in t["ticks"]],
    }.items():
        altered = copy.deepcopy(traces[0])
        edit(altered)
        mutations[name] = checker.check_trace(altered, manifest, digest, worlds[altered["world_id"]], manifest["budgets"])
    with tempfile.TemporaryDirectory(prefix="ag01-correction-review-") as tmp:
        for f in files:
            (Path(tmp) / f.name).write_bytes(f.read_bytes())
        (Path(tmp) / "duplicate.json").write_bytes(files[0].read_bytes())
        duplicate = checker.check_dir(tmp, manifest, digest, manifest["budgets"], expect_full=True)
    altered_manifest = copy.deepcopy(manifest)
    altered_manifest["analysis_rule"] = "changed without changing supplied digest"
    drift = checker.check_dir(package / "results_v2", altered_manifest, digest, manifest["budgets"], expect_full=True)
    deficits = [{"trajectory": t["traj_id"], "decisions": len(t["ticks"]),
                 "paid_decisions": sum(r["amount"] for r in t["ledger"]["reservations"] if ":dec:" in r["operation_id"])}
                for t in traces]
    deficits = [d for d in deficits if d["decisions"] != d["paid_decisions"]]
    args = replay.build_parser().parse_args([
        "run", "--base-dsn", "unused", "--world", "w25", "--arm", "R",
        "--tie", "0", "--manifest-hash", digest, "--out-dir", "unused"])
    backend = DecisionBackend()
    st = {"deps": {}, "options": {}, "launched": {}, "scored": [], "products": {},
          "drained_products": [], "drained": [], "refused": [], "admitted_fx": {},
          "ticks": [], "idle": 0, "feasible_wait": 0, "liabilities": []}
    world = {"world_id": "review", "ticks": 2, "seeds": [], "events": [], "instruments": {}}
    with patch.object(runner, "_rebuild_state", return_value=st), \
            patch.object(runner, "_candidates", return_value=[]), \
            patch.object(runner, "_policy_state", return_value={}):
        runner._drive(world, "R", 0, lambda packet: {"decision": "idle"}, "AG01-R-1",
                      {"tie_orders": {}}, "review", {"decision_cost": 1}, backend, max_ticks=1)
    print(json.dumps({
        "source": "051811fd59ab6d1de0f85a1be8849e94b638ebf5",
        "scope": "stored traces, pure checker/CLI parser, actual driver with a memory backend double; no PostgreSQL replay",
        "strict_checker": {"ok": original["ok"], "traces": original["traces"], "pairs": len(original["pairs"])},
        "operation_rows": sum(len(t["ledger"]["ops"]) for t in traces),
        "totals": {arm: {"grade": sum(t["grade"]["correct"] for t in traces if t["arm"] == arm),
                         "exploration": sum(t["totals"]["explore_spent"] for t in traces if t["arm"] == arm)}
                   for arm in ("R", "Q")},
        "free_decisions": sum(d["decisions"] - d["paid_decisions"] for d in deficits),
        "decision_deficits": deficits,
        "mutation_checker_reasons": mutations,
        "duplicate_trace_accepted": {"ok": duplicate["ok"], "traces": duplicate["traces"]},
        "altered_manifest_accepted": drift["ok"],
        "resume_flag_in_existing_test_command": args.resume,
        "driver_save": {"next_tick": backend.saved["next_tick"], "recorded_ticks": len(backend.saved["ticks"]),
                        "in_memory_ticks_after_save": len(st["ticks"]), "idle_count": backend.saved["idle"]},
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
