"""BDR-03 slice 1: admission validates the full action target.

Rejecting tests for review finding BDR-03: _run_boundary executed the
proposal's target after admit_investigation checked only basis
references, so a development proposal citing an ordinary observation
could target a protected-use task (or another world) and run. No DB;
all effects are visible in the returned campaign.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 1, "diagnostic_queries": 16}


def _targeting(target: str, kind: str = "development"):
    def propose(experience, charter):
        seed = experience["observations"][0]
        return {"basis_references": [seed["observation_id"]],
                "question": "inspect %s" % target,
                "next_action": {"kind": kind, "diagnostic": "software",
                                "task_id": target},
                "requested_resources": {"diagnostic_queries": 1}}
    return propose


def test_protected_use_target_refuses_before_work():
    from experiments.ad01 import trajectory
    campaign = trajectory.run_campaign(
        0, "I", CHARTER, dict(CAPS),
        tasks=["ad01-w0-dev-sw-00"],
        propose=_targeting("ad01-w0-within-sw-00"))
    [episode] = campaign["episodes"]
    assert episode["task_id"] == "ad01-w0-dev-sw-00"
    assert episode["disposition"] == "no-candidate"
    assert "protected-use" in episode["fallback_reason"]
    assert episode["queries"] == 0
    [boundary] = campaign["boundaries"]
    assert boundary["observation_id"] == "obs-ad01-w0-dev-sw-00-seed", \
        "a diagnostic ran before the refusal"


def test_cross_world_target_refuses_before_work():
    from experiments.ad01 import trajectory
    campaign = trajectory.run_campaign(
        0, "I", CHARTER, dict(CAPS),
        tasks=["ad01-w0-dev-sw-00"],
        propose=_targeting("ad01-w1-dev-sw-00"))
    [episode] = campaign["episodes"]
    assert episode["disposition"] == "no-candidate"
    assert episode["queries"] == 0


def test_unknown_target_refuses_before_work():
    from experiments.ad01 import trajectory
    campaign = trajectory.run_campaign(
        0, "I", CHARTER, dict(CAPS),
        tasks=["ad01-w0-dev-sw-00"],
        propose=_targeting("not-a-task"))
    [episode] = campaign["episodes"]
    assert episode["disposition"] == "no-candidate"
    assert episode["queries"] == 0


def test_r_arm_outside_curriculum_refuses():
    from experiments.ad01 import trajectory
    campaign = trajectory.run_campaign(
        0, "R", CHARTER, dict(CAPS),
        tasks=["ad01-w0-dev-sw-01"],
        propose=_targeting("ad01-w0-dev-sw-01"))
    [episode] = campaign["episodes"]
    assert episode["disposition"] == "no-candidate"
    assert "curriculum" in episode["fallback_reason"]
    assert episode["queries"] == 0


def test_r_arm_curriculum_item_dispatches():
    from experiments.ad01 import rotation, trajectory
    first = rotation.r_schedule(0)[0]["task_id"]
    campaign = trajectory.run_campaign(
        0, "R", CHARTER, dict(CAPS), tasks=[first],
        propose=_targeting(first))
    assert campaign["episodes"][0]["task_id"] == first
    assert campaign["episodes"][0]["disposition"] != "no-candidate" or \
        "curriculum" not in campaign["episodes"][0].get("fallback_reason",
                                                        "")


def test_legitimate_dev_target_still_succeeds():
    from experiments.ad01 import trajectory
    campaign = trajectory.run_campaign(
        0, "I", CHARTER, dict(CAPS),
        tasks=["ad01-w0-dev-sw-00"],
        propose=_targeting("ad01-w0-dev-sw-01"))
    assert campaign["episodes"][0]["task_id"] == "ad01-w0-dev-sw-01"
