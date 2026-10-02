"""Read-only assessment of the batch evidence and unfinished study seams."""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from experiments.agenda01 import checker as agenda_checker, manifest as agenda_manifest
from experiments.representation.acquire import live_campaign, panel
from experiments.representation.experiment import checker, freeze


def assess():
    agenda_root = ROOT / "experiments/agenda01"
    manifest = json.loads((agenda_root / "manifest_v3.json").read_bytes())
    digest = (agenda_root / "manifest_v3.sha256").read_text().strip()
    agenda = agenda_checker.check_dir(agenda_root / "results_v3", manifest,
                                      digest, manifest["budgets"], expect_full=True)
    try:
        agenda_manifest.load_verified(agenda_root / "manifest_v3.json",
                                      agenda_root / "manifest_v3.sha256")
        source_check = "verified"
    except (ValueError, OSError) as exc:
        source_check = str(exc)
    representation = checker.check_all(ROOT / "experiments/representation/evidence")
    synthetic = {(arm, family): {"family": family,
                 "result": {"improvement_u": 0.7 if family == "software"
                            else (0.4 if arm == "C" else 0.2), "verified": True},
                 "costs": {"elapsed_s": 1_000_000 if arm == "C" else 1,
                           "queries_used": 1, "model_calls": 0,
                           "model_tokens": {"in": 0, "out": 0}}}
                 for arm in "ABC" for family in ("software", "graph")}
    live = live_campaign.preflight({live_campaign.ENDPOINT_ENV: "https://example.invalid/v1",
                                   live_campaign.KEY_ENV: "non-secret-probe-placeholder",
                                   live_campaign.GRANT_ENV: "1"})
    return {"reviewed_revision": "324174f4e98890c95c25bca039feec267a061e8a",
            "scope": "stored evidence, source checks and synthetic decision probe; no DB or inference",
            "agenda": {"traces": agenda["traces"], "pairs": len(agenda["pairs"]),
                       "ok": agenda["ok"], "violations": agenda["violations"],
                       "source_check": source_check,
                       "totals": {key: sum(pair[key] for pair in agenda["pairs"])
                                  for key in ("correct_r", "correct_q", "explore_r", "explore_q")}},
            "representation": representation,
            "representation_regeneration": freeze.verify_committed(),
            "representation_panel": {"benefit_tasks": panel.BENEFIT_SW + panel.BENEFIT_GR,
                                     "groups": sorted({panel.trial_group(t)
                                                       for t in panel.BENEFIT_SW + panel.BENEFIT_GR}),
                                     "required_heldout_benefit_tasks": 16,
                                     "observed_heldout_benefit_tasks": 0},
            "configured_live_preflight": {key: live[key] for key in ("blocked", "reason", "spent")},
            "resource_counterexample": {"synthetic_only": True, "C_elapsed_ratio": 1_000_000,
                                        "required_max_ratio": 1.25,
                                        "decision": checker.pilot_rule(synthetic)},
            "sources": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                        for name in ("experiments/representation/acquire/live_campaign.py",
                                     "experiments/representation/acquire/panel.py",
                                     "experiments/representation/experiment/checker.py")}}


if __name__ == "__main__":
    result = json.dumps(assess(), indent=2, sort_keys=True) + "\n"
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(result, encoding="utf-8", newline="\n")
    else:
        print(result, end="")
