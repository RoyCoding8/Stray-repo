"""AD01-LEARN-C: development episodes run acquired bytes; load verifies.

dev_episode must execute an acquired repertoire member's own bytes
through the same retained/rejected rules as seeds, and loading a
repertoire must refuse tampered acquired bytes. No DB.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEV_TASK = "ad01-w0-dev-sw-00"

ACQUIRED_SOURCE = (
    "def acquired_order(task, oracle, max_queries=16):\n"
    "    return reducers.reduce_software(task, oracle, method=\"greedy\","
    " max_queries=max_queries)\n"
)

BROKEN_SOURCE = (
    "def broken_add(task, oracle, max_queries=16):\n"
    "    cand = dict(task)\n"
    "    cand['ops'] = list(task['ops']) + [{'op': 'set', 'id': 'x',"
    " 'key': 'k'}]\n"
    "    return {'candidate': cand, 'queries': 0}\n"
)


def _member(source: str, entry: str, capability_id: str) -> dict:
    return {"capability_id": capability_id, "method_source": source,
            "entry": entry, "params": {"max_queries": 16},
            "scope": {"family": "software"}, "authored": False,
            "qualified_on": DEV_TASK,
            "source_digest": hashlib.sha256(
                source.encode("utf-8")).hexdigest(),
            "lineage": {"campaign_id": "alec", "lineage": 1,
                        "init_operation": "op-init",
                        "repair_operation": None,
                        "init_failure": None, "calls_made": 1}}


def test_episode_runs_acquired_bytes_and_retains():
    from experiments.ad01 import trajectory
    member = _member(ACQUIRED_SOURCE, "acquired_order",
                     "acquired-sw-test01")
    episode = trajectory.dev_episode(DEV_TASK, "seed-sw-greedy",
                                     max_queries=16, member=member)
    assert episode["disposition"] == "retained"
    assert episode["executable"]["method_source"] == ACQUIRED_SOURCE
    assert episode["executable"]["authored"] is False
    assert episode["executable"]["capability_id"] == "acquired-sw-test01"
    assert all(not e.get("authored", True)
               for e in episode["lineage"]
               if e.get("capability_id") == "acquired-sw-test01")
    assert episode["final_size"] < episode["initial_size"]


def test_episode_rejects_invalid_acquired_bytes():
    from experiments.ad01 import trajectory
    member = _member(BROKEN_SOURCE, "broken_add", "acquired-sw-broken")
    episode = trajectory.dev_episode(DEV_TASK, "seed-sw-greedy",
                                     max_queries=16, member=member)
    assert episode["disposition"] == "rejected"
    assert episode["reason"]


def test_freeze_load_round_trips_acquired_bytes(tmp_path):
    from experiments.ad01 import trajectory
    member = _member(ACQUIRED_SOURCE, "acquired_order",
                     "acquired-sw-test01")
    campaign = {"campaign_id": "alec",
                "episodes": [{"disposition": "retained",
                               "executable": member}]}
    frozen = tmp_path / "repertoire.json"
    trajectory.freeze_repertoire(campaign, frozen)
    loaded = trajectory.load_repertoire(frozen)
    assert loaded["members"][0]["method_source"] == ACQUIRED_SOURCE
    assert loaded["members"][0]["source_digest"] == member[
        "source_digest"]


def test_load_refuses_tampered_acquired_bytes(tmp_path):
    import pytest
    from experiments.ad01 import trajectory
    member = _member(ACQUIRED_SOURCE, "acquired_order",
                     "acquired-sw-test01")
    tampered = dict(member, method_source=ACQUIRED_SOURCE + "# x\n")
    campaign = {"campaign_id": "alec",
                "episodes": [{"disposition": "retained",
                               "executable": tampered}]}
    frozen = tmp_path / "repertoire.json"
    trajectory.freeze_repertoire(campaign, frozen)
    with pytest.raises(ValueError, match="do not match their digest"):
        trajectory.load_repertoire(frozen)


def test_seed_episodes_unchanged_without_member():
    from experiments.ad01 import trajectory
    episode = trajectory.dev_episode(DEV_TASK, "seed-sw-greedy",
                                     max_queries=16)
    assert episode["disposition"] == "retained"
    assert episode["executable"]["authored"] is True
    assert "method_source" not in episode["executable"]
