"""B-ACQ slice 1: outside-menu retained bytes execute, never seed lookup.

A retained repertoire member whose capability_id is NOT in
SEED_CAPABILITIES but whose bytes are executable must run its own bytes
through freeze/load/use. Seed-menu lookup by id (StopIteration today) or
silent incumbent fallback would fail this test.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

MEMBER_ID = "acquired-sw-greedy-r1"
METHOD_SOURCE = (
    "def acquired_reduce(task, oracle, max_queries=16):\n"
    "    return reducers.reduce_software(task, oracle, method=\"greedy\","
    " max_queries=max_queries)\n"
)
USE_TASK = "ad01-w0-within-sw-00"


def _member() -> dict:
    return {"capability_id": MEMBER_ID, "method_source": METHOD_SOURCE,
            "entry": "acquired_reduce", "params": {"max_queries": 16},
            "scope": {"family": "software"}, "authored": False,
            "qualified_on": "ad01-w0-dev-sw-00",
            "source_digest": hashlib.sha256(
                METHOD_SOURCE.encode("utf-8")).hexdigest(),
            "lineage": {"campaign_id": "bacq-slice1", "lineage": 1,
                        "init_operation": "op-init",
                        "repair_operation": None, "init_failure": None,
                        "calls_made": 1}}


def test_run_use_executes_outside_menu_member_bytes(tmp_path):
    from experiments.ad01 import seeds, trajectory, worlds
    member = _member()
    campaign = {"campaign_id": "bacq-slice1",
                "episodes": [{"disposition": "retained",
                               "executable": member}]}
    frozen = tmp_path / "repertoire.json"
    trajectory.freeze_repertoire(campaign, frozen)
    repertoire = trajectory.load_repertoire(frozen)
    assert repertoire["members"][0] == member
    [record] = trajectory.run_use(
        repertoire, 0, "I", [USE_TASK], {"tokens": 0, "sandbox_ops": 0})
    assert record["requested"] == MEMBER_ID
    assert record["selected"] == MEMBER_ID
    assert record["executed"] == MEMBER_ID
    assert record["executed_source"] == member["method_source"]
    assert record["fallback_reason"] == ""
    task = worlds.load_task(worlds.FROZEN_DIR, USE_TASK)
    seed = next(c for c in seeds.SEED_CAPABILITIES
                if c["capability_id"] == "seed-sw-greedy")
    expected = seeds.run_seed(seed, task, max_queries=16)
    assert record["output"] == expected["candidate"]
    assert record["verdict"] == "preserved"
