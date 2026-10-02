"""INV-G3: construction observes the just-produced diagnostic result.

Review IR-01 (EC02-AD01-84D2094 assessment): `_run_boundary` ran the
diagnostic but forwarded the earlier `seen` packet to construction, so
the fresh observation never reached the construction prompt. The
constructor must see accumulated diagnostics including the one just
produced on this boundary. No DB; the constructor is doubled at the
`construct_method` seam and the real diagnostic runs locally.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GRAPH_TASK = "ad01-w0-dev-gr-00"


def _develop(task_id: str, requested: int):
    def propose(seen, asked):
        seed = seen["observations"][0]
        return {"basis_references": [seed["observation_id"]],
                "question": "develop %s" % task_id,
                "next_action": {"kind": "development",
                                "diagnostic": "graph",
                                "task_id": task_id,
                                "max_queries": requested},
                "requested_resources": {"diagnostic_queries": 1}}
    return propose


def _boundary_args(task_id: str):
    from experiments.ad01 import trajectory as T
    seed_obs = {"observation_id": "obs-%s-seed" % task_id,
                "task_id": task_id, "capability_id": "seed-gr-greedy",
                "verdict": "unmeasured"}
    experience = {"observations": [], "retained": [],
                  "remaining": {"queries": 16, "model_calls": 60}}
    state = {"dev_episodes": 0, "model_calls": 0,
             "construction_calls": 0}
    return T, seed_obs, experience, state


def test_construction_receives_fresh_diagnostic_observation(
        monkeypatch):
    from experiments.ad01 import construct as C
    captured = {}

    def fake_construct(dsn, *, campaign_id, task, experience, budget,
                       gateway, model):
        captured["observations"] = list(
            experience.get("observations") or [])
        return {"capability_id": "acquired-gr-x",
                "method_source": "s", "source_digest": "d",
                "lineage": {"calls_made": 0},
                "validation": {"result": {"candidate": task,
                                          "queries": 0}}}

    monkeypatch.setattr(C, "construct_method", fake_construct)
    T, seed_obs, experience, state = _boundary_args(GRAPH_TASK)
    observation, episode, spend = T._run_boundary(
        GRAPH_TASK, "seed-gr-greedy",
        {"diagnostic_queries": 16, "model_calls": 60}, seed_obs,
        propose=_develop(GRAPH_TASK, 5),
        charter={"objective": "x"},
        boundary={"world": 0, "arm": "I", "seq": 0},
        experience=experience, state=state,
        construction={"dsn": None, "cid": "probe", "gateway": None,
                      "model": "", "model_cap": 60, "budget": {}},
        journal={"dsn": None, "cid": None, "decision": None})
    visible = [o.get("observation_id")
               for o in captured["observations"]]
    assert seed_obs["observation_id"] in visible
    assert observation["observation_id"] in visible
    fresh = [o for o in captured["observations"]
             if o.get("observation_id") == observation["observation_id"]]
    assert fresh and fresh[0].get("detail") is not None
