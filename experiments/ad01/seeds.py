"""Seed repertoire: supplied reducers as labeled authored capabilities.

The ddmin and greedy reducers from representation-01/1 are the experiment's
initial repertoire. They are labeled authored here so no later trajectory
can present their behavior as acquired. T-ADTR consumes these records.
"""

from __future__ import annotations

from experiments.representation import checkers, reducers
from experiments.representation.splits import AD01_FREEZE_ID

SEED_CAPABILITIES = [
    {"capability_id": "seed-sw-ddmin", "family": "software",
     "method": "ddmin", "authored": True, "origin": "supplied-rpr01",
     "freeze": AD01_FREEZE_ID},
    {"capability_id": "seed-sw-greedy", "family": "software",
     "method": "greedy", "authored": True, "origin": "supplied-rpr01",
     "freeze": AD01_FREEZE_ID},
    {"capability_id": "seed-gr-ddmin", "family": "graph",
     "method": "ddmin", "authored": True, "origin": "supplied-rpr01",
     "freeze": AD01_FREEZE_ID},
    {"capability_id": "seed-gr-greedy", "family": "graph",
     "method": "greedy", "authored": True, "origin": "supplied-rpr01",
     "freeze": AD01_FREEZE_ID},
]

_KNOWN = {c["capability_id"]: c for c in SEED_CAPABILITIES}


def run_seed(capability: dict, task: dict, *, max_queries: int = 16) -> dict:
    known = _KNOWN.get(capability.get("capability_id", ""))
    if known is None or capability.get("family") != task.get("family"):
        raise KeyError(capability.get("capability_id"))
    oracle = (checkers.SoftwareOracle(task, max_queries=max_queries)
              if task["family"] == "software"
              else checkers.GraphOracle(task, max_queries=max_queries))
    reduce = (reducers.reduce_software if task["family"] == "software"
              else reducers.reduce_graph)
    result = reduce(task, oracle, method=known["method"],
                    max_queries=max_queries)
    result["capability_id"] = known["capability_id"]
    return result
