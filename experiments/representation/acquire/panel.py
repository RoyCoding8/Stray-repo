"""Frozen panel, selectors and budgets for the Representation Lane D pilot.

Single source of truth imported by the freeze script, the runner, the
checker and the replay CLI, so the three can never disagree about panel
membership. Selectors are derived from development transcripts only.

RPR-ACQ/2 is the held-out evaluation freeze: sixteen benefit tasks (eight
software, eight graph) drawn from the lane B evaluation split, whose
seeds and structural patterns never entered development, check, context
or selector construction. The RPR-ACQ/1 authored-mechanics membership
(MECHANICS_*/ACQUIRE_*) is retained below for provenance; it is no
longer the benefit panel.
"""

from __future__ import annotations

import sys
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

PANEL_VERSION = "RPR-ACQ/2"
CHECKER_VERSION = "rpr-checker/1"

MECHANICS_SW = ["sw-dev-%02d" % i for i in range(4)]
MECHANICS_GR = ["gr-dev-%02d" % i for i in range(3)]
ACQUIRE_SW = ["sw-che-00"]
ACQUIRE_GR = ["gr-che-00"]
HELDOUT_SW = ["sw-eva-%02d" % i for i in range(8)]
HELDOUT_GR = ["gr-eva-%02d" % i for i in range(8)]
BENEFIT_SW = list(HELDOUT_SW)
BENEFIT_GR = list(HELDOUT_GR)
CONTROLS = ["ctrl-sw-wrong-obs", "ctrl-sw-invalid", "ctrl-gr-triangle",
            "ctrl-gr-bipartite"]
USE = ["use-sw-supported", "use-gr-supported", "use-sw-out-of-scope",
       "use-gr-out-of-scope"]
ATTRIBUTION = [("sw-dev-04", "software"), ("gr-dev-03", "graph")]

ARMS = ("A", "B", "C")
BUDGETS = {"witness_queries": 16, "validation_queries": 2,
           "component_invocations": 64, "elapsed_s": 120,
           "per_invocation_ms": 2000, "message_bytes": 65536,
           "max_advances": 8, "model_calls": 0}

EPISODE_SOURCE = "rpr-acq-source"
EPISODE_TRANSFER = "rpr-acq-transfer"
PROTOCOL_B = "rpr-acq-B"
PROTOCOL_C = "rpr-acq-C"

COMPONENTS = {"core": "acquire/atom_core.py",
              "sw_adapter": "acquire/sw_adapter.py",
              "gr_adapter": "acquire/gr_adapter.py",
              "null_core": "acquire/null_core.py",
              "sw_checker": "experiment/bundle_sw_checker.py",
              "gr_checker": "experiment/bundle_gr_checker.py"}

DOMAIN_SPECS = {
    "software": {"family": "software", "witness": "value-disagreement",
                 "measure": "ops"},
    "graph": {"family": "graph", "witness": "triangle-free-non-bipartite",
              "measure": "vertices-edges"},
}


def derive_selectors(source_ctx: dict, transfer_ctx: dict) -> dict:
    def bucketed(ctx):
        measures = sorted(x["measure"] for x in ctx["tasks"])
        threshold = median(measures)
        small = [x["task_id"] for x in ctx["tasks"]
                 if x["measure"] <= threshold]
        large = [x["task_id"] for x in ctx["tasks"]
                 if x["measure"] > threshold]
        return threshold, {"small": small, "large": large}

    selectors = {"arm-A": {}, "arm-B": {}}
    for ctx, family in ((source_ctx, "software"), (transfer_ctx, "graph")):
        threshold, buckets = bucketed(ctx)
        pick = {}
        for bucket, ids in buckets.items():
            scored = []
            for method in ("ddmin", "greedy"):
                runs = [ctx["transcripts"][i][method] for i in ids]
                mean_u = sum(r["final_u"] for r in runs) / len(runs)
                queries = sum(r["queries"] for r in runs)
                scored.append((method, round(mean_u, 6), queries))
            scored.sort(key=lambda row: (-row[1], row[2], row[0]))
            pick[bucket] = {"method": scored[0][0], "mean_u": scored[0][1],
                            "queries": scored[0][2],
                            "runner_up": {"method": scored[1][0],
                                          "mean_u": scored[1][1],
                                          "queries": scored[1][2]}}
        family_mean = {}
        for method in ("ddmin", "greedy"):
            runs = [r[method] for r in ctx["transcripts"].values()]
            family_mean[method] = round(sum(r["final_u"] for r in runs)
                                       / len(runs), 6)
        best = max(("ddmin", "greedy"), key=lambda m: family_mean[m])
        selectors["arm-A"][family] = {"method": best, "mean_u": family_mean[best]}
        selectors["arm-B"][family] = {"threshold": threshold, "buckets": pick}
    return selectors


def benefit_pairs() -> list:
    pairs = []
    for task_id in BENEFIT_SW + BENEFIT_GR:
        for arm in ARMS:
            pairs.append({"arm": arm, "task_id": task_id})
    return pairs


def control_pairs() -> list:
    return [{"arm": arm, "task_id": task_id}
            for task_id in CONTROLS for arm in ARMS]


def trial_group(task_id: str) -> str:
    if task_id in MECHANICS_SW + MECHANICS_GR:
        return "development"
    if task_id in HELDOUT_SW + HELDOUT_GR:
        return "protected-eval"
    return "check"
