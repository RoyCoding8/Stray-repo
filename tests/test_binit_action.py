from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 6, "diagnostic_queries": 16}


def selecting_propose(experience, charter):
    seed = experience["observations"][0]
    return {"basis_references": [seed["observation_id"]],
            "question": "try the other visible task",
            "next_action": {"kind": "development",
                            "task_id": "ad01-w0-dev-sw-01"},
            "requested_resources": {"diagnostic_queries": 1}}


def test_accepted_action_selects_dispatched_task():
    from experiments.ad01 import trajectory
    campaign = trajectory.run_campaign(
        0, "I", CHARTER, dict(CAPS, max_boundaries=1),
        tasks=["ad01-w0-dev-sw-00"], propose=selecting_propose)
    assert campaign["boundaries"][0]["task_id"] == "ad01-w0-dev-sw-01"
    assert campaign["episodes"][0]["task_id"] == "ad01-w0-dev-sw-01"
