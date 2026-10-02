import copy
import json
import runpy
import tempfile
from pathlib import Path

from experiments.agenda01 import checker


def main():
    root = Path(__file__).resolve().parents[2]
    package = root / "experiments/agenda01"
    manifest = json.loads((package / "manifest.json").read_text())
    digest = (package / "manifest.sha256").read_text().strip()
    traces = [json.loads(p.read_text()) for p in sorted((package / "results").glob("*.json"))]
    worlds = {w["world_id"]: w for w in manifest["worlds"]}
    report = checker.check_dir(package / "results", manifest, digest, manifest["budgets"])
    specimen = traces[0]
    mutations = {}
    for name, edit in {
        "marked_incomplete": lambda t: t.update(complete=False),
        "false_policy_version": lambda t: t.update(policy_version="not-the-frozen-policy"),
        "missing_eval_reservations": lambda t: t["ledger"].update(reservations=[
            r for r in t["ledger"]["reservations"] if not r["allocation_id"].endswith(":eval")]),
        "missing_decision_operations": lambda t: [tick.update(dec_op=None) for tick in t["ticks"]],
    }.items():
        altered = copy.deepcopy(specimen)
        edit(altered)
        mutations[name] = checker.check_trace(altered, digest, worlds[altered["world_id"]], manifest["budgets"])
    with tempfile.TemporaryDirectory(prefix="ag01-review-") as tmp:
        empty = checker.check_dir(tmp, manifest, digest, manifest["budgets"])
    helpers = runpy.run_path(str(root / "tests/test_ag01_policy.py"))
    unrelated = helpers["qualify_continuation"](
        helpers["_cont"](cited=[helpers["_cite"](prop="unrelated")],
                         next_probe=helpers["_probe"](outcomes=[])),
        [helpers["_obs"](prop="unrelated")], helpers["_state"]())
    pairs = {(t["world_id"], t["tie"]): {} for t in traces}
    for t in traces:
        pairs[t["world_id"], t["tie"]][t["arm"]] = t
    differences = sum(a["decision"]["action"] != b["decision"]["action"] or
                      a["decision"]["option_key"] != b["decision"]["option_key"]
                      for arms in pairs.values() for a, b in zip(arms["R"]["ticks"], arms["Q"]["ticks"]))
    print(json.dumps({
        "source": "29496a04d5f1d7754a7ea7b623e4a1d0f1b1c25e",
        "scope": "preserved artifacts and pure Python; no PostgreSQL or live trajectory replay",
        "original_checker": {"ok": report["ok"], "traces": report["traces"], "pairs": len(report["pairs"])},
        "all_pair_grades_tied": all(v["R"]["grade"] == v["Q"]["grade"] for v in pairs.values()),
        "all_pair_resource_vectors_tied": all(v["R"]["totals"] == v["Q"]["totals"] for v in pairs.values()),
        "action_or_option_differences": differences,
        "runtime_operation_rows": sum(len(t["ledger"]["ops"]) for t in traces),
        "empty_directory_accepted": empty["ok"],
        "mutation_checker_reasons": mutations,
        "irrelevant_citation_qualification": unrelated,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
