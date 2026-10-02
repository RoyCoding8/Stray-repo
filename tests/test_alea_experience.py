"""AD01-LEARN-A: accumulated experience, inspection boundaries, caps.

The learner packet must carry accumulated permitted experience (not one
seed observation); diagnostic-kind work inspects without consuming
construction capacity; per-trajectory development-episode and diagnostic
budgets gate new work. No DB.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}

DEV_TASKS = ["ad01-w0-dev-sw-00", "ad01-w0-dev-sw-01",
             "ad01-w0-dev-sw-02", "ad01-w0-dev-gr-00"]


def _develop(target: str, max_queries: int = 2, kind: str = "development"):
    def propose(experience, charter):
        seed = experience["observations"][0]
        return {"basis_references": [seed["observation_id"]],
                "question": "work %s" % target,
                "next_action": {"kind": kind, "diagnostic": "software",
                                "task_id": target,
                                "max_queries": max_queries},
                "requested_resources": {"diagnostic_queries": 1}}
    return propose


def test_next_packet_carries_accumulated_experience():
    from experiments.ad01 import trajectory
    seen_lengths = []

    def propose(experience, charter):
        seen_lengths.append(len(experience["observations"]))
        seed = experience["observations"][0]
        target = DEV_TASKS[len(seen_lengths) - 1]
        return {"basis_references": [seed["observation_id"]],
                "question": "work %s" % target,
                "next_action": {"kind": "diagnostic", "diagnostic": "software",
                                "task_id": target},
                "requested_resources": {}}

    campaign = trajectory.run_campaign(
        0, "I", CHARTER, {"max_boundaries": 2, "diagnostic_queries": 16},
        tasks=DEV_TASKS[:2], propose=propose)
    assert seen_lengths == [1, 2], seen_lengths
    assert len(campaign["boundaries"]) == 2


def test_diagnostic_cites_prior_result_and_grounds_it():
    from experiments.ad01 import trajectory
    calls = []

    def propose(experience, charter):
        calls.append([o["observation_id"]
                      for o in experience["observations"]])
        if len(experience["observations"]) == 1:
            seed = experience["observations"][0]
            return {"basis_references": [seed["observation_id"]],
                    "question": "first look",
                    "next_action": {"kind": "diagnostic",
                                    "diagnostic": "software",
                                    "task_id": DEV_TASKS[0]},
                    "requested_resources": {}}
        prior = experience["observations"][-1]["observation_id"]
        seed = experience["observations"][0]
        return {"basis_references": [seed["observation_id"], prior],
                "question": "follow the prior result",
                "next_action": {"kind": "diagnostic",
                                "diagnostic": "software",
                                "task_id": DEV_TASKS[1]},
                "requested_resources": {}}

    campaign = trajectory.run_campaign(
        0, "I", CHARTER, {"max_boundaries": 2, "diagnostic_queries": 16},
        tasks=DEV_TASKS[:2], propose=propose)
    assert len(calls[1]) == 2
    second = campaign["boundaries"][1]
    assert second["task_id"] == DEV_TASKS[1]
    assert campaign["episodes"][1]["disposition"] == "inspected"


def test_diagnostic_boundary_inspects_without_episode():
    from experiments.ad01 import trajectory
    campaign = trajectory.run_campaign(
        0, "I", CHARTER, {"max_boundaries": 1, "diagnostic_queries": 16},
        tasks=[DEV_TASKS[1]], propose=_develop(DEV_TASKS[1], kind="diagnostic"))
    [episode] = campaign["episodes"]
    assert episode["disposition"] == "inspected"
    assert episode["queries"] == 0
    assert campaign["boundaries"][0]["spend"] == 1
    assert "executable" not in episode and "check" not in episode
    assert campaign.get("dev_episodes", None) == 0


def test_development_episode_cap_refuses_the_fourth():
    from experiments.ad01 import trajectory

    def propose(experience, charter):
        seed = experience["observations"][0]
        target = DEV_TASKS[len(experience["observations"]) - 1]
        family = "graph" if "-gr-" in target else "software"
        return {"basis_references": [seed["observation_id"]],
                "question": "develop %s" % target,
                "next_action": {"kind": "development",
                                "diagnostic": family,
                                "task_id": target, "max_queries": 2},
                "requested_resources": {"diagnostic_queries": 1}}

    campaign = trajectory.run_campaign(
        0, "I", CHARTER, {"max_boundaries": 6, "diagnostic_queries": 16},
        tasks=list(DEV_TASKS), propose=propose)
    assert [e["disposition"] for e in campaign["episodes"][:3]] != \
        ["no-candidate"] * 3
    fourth = campaign["episodes"][3]
    assert fourth["disposition"] == "no-candidate"
    assert "episode cap" in fourth["fallback_reason"]
    assert fourth["queries"] == 0
    assert campaign["dev_episodes"] == 3


def test_diagnostic_query_cap_stops_the_trajectory():
    from experiments.ad01 import trajectory
    campaign = trajectory.run_campaign(
        0, "I", CHARTER, {"max_boundaries": 6, "diagnostic_queries": 16},
        tasks=list(DEV_TASKS), propose=_develop(DEV_TASKS[0],
                                               max_queries=16))
    assert campaign["queries"] >= 16
    assert campaign["stop"]["reason"] == "diagnostic query cap reached"


def test_unknown_action_kind_refuses():
    from experiments.ad01 import trajectory
    campaign = trajectory.run_campaign(
        0, "I", CHARTER, {"max_boundaries": 1, "diagnostic_queries": 16},
        tasks=[DEV_TASKS[0]], propose=_develop(DEV_TASKS[0], kind="dream"))
    [episode] = campaign["episodes"]
    assert episode["disposition"] == "no-candidate"
    assert "unknown action kind" in episode["fallback_reason"]
    assert episode["queries"] == 0
