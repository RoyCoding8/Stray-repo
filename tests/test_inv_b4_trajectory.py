"""INV-B4: kill the IR-03 double promise at the trajectory caller.

Remaining 6 with diagnostic granted 5 and spent 4 must sequence
construction to 1, never re-grant 5. A zero-budget probe is refused
through the loop refusal path and consumes no study lineage.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from settlement.loop import ResourceEnvelope

GRAPH_TASK = "ad01-w0-dev-gr-00"
SW_TASK = "ad01-w0-dev-sw-00"
REMAINING = 6


def _develop(task_id: str, requested: int):
    def propose(seen, asked):
        seed = seen["observations"][0]
        return {"basis_references": [seed["observation_id"]],
                "question": "develop %s" % task_id,
                "next_action": {"kind": "development",
                                "diagnostic": ("graph" if "-gr-" in task_id
                                               else "software"),
                                "task_id": task_id,
                                "max_queries": requested},
                "requested_resources": {"diagnostic_queries": 1}}
    return propose


def _boundary_args(task_id: str):
    from experiments.ad01 import trajectory as T
    capability = ("seed-gr-greedy" if "-gr-" in task_id
                  else "seed-sw-greedy")
    seed_obs = {"observation_id": "obs-%s-seed" % task_id,
                "task_id": task_id, "capability_id": capability,
                "verdict": "unmeasured"}
    experience = {"observations": [], "retained": [],
                  "remaining": {"queries": REMAINING, "model_calls": 60}}
    state = {"dev_episodes": 0, "model_calls": 0,
             "construction_calls": 0}
    return T, capability, seed_obs, experience, state


def test_construction_sequences_from_remaining_minus_diagnostic_spend(
        monkeypatch):
    from experiments.ad01 import construct as C
    captured = {}

    def fake_construct(dsn, *, campaign_id, task, experience, budget,
                       gateway, model):
        captured.update(dict(budget))
        return {"capability_id": "acquired-gr-x",
                "method_source": "s", "source_digest": "d",
                "lineage": {"calls_made": 0},
                "validation": {"result": {"candidate": task,
                                          "queries": 0}}}

    monkeypatch.setattr(C, "construct_method", fake_construct)
    T, capability, seed_obs, experience, state = _boundary_args(
        GRAPH_TASK)
    observation, episode, spend = T._run_boundary(
        GRAPH_TASK, capability,
        {"diagnostic_queries": 16, "model_calls": 60}, seed_obs,
        propose=_develop(GRAPH_TASK, 5),
        charter={"objective": "x"},
        boundary={"world": 0, "arm": "I", "seq": 0},
        experience=experience, state=state,
        construction={"dsn": None, "cid": "probe", "gateway": None,
                      "model": "", "model_cap": 60, "budget": {}},
        journal={"dsn": None, "cid": None, "decision": None})
    assert observation["queries"] == 4
    sequenced = ResourceEnvelope.sequence_construction_allowance(
        REMAINING, observation["queries"])
    assert sequenced == 1
    assert captured["max_queries"] == sequenced == 1
    assert spend <= REMAINING


def test_diagnostic_spend_reduces_construction_allowance(monkeypatch):
    from experiments.ad01 import construct as C
    captured = {}

    def fake_construct(dsn, *, campaign_id, task, experience, budget,
                       gateway, model):
        captured.update(dict(budget))
        return {"capability_id": "acquired-sw-x",
                "method_source": "s", "source_digest": "d",
                "lineage": {"calls_made": 0},
                "validation": {"result": {"candidate": task,
                                          "queries": 0}}}

    monkeypatch.setattr(C, "construct_method", fake_construct)
    T, capability, seed_obs, experience, state = _boundary_args(SW_TASK)
    observation, episode, spend = T._run_boundary(
        SW_TASK, capability,
        {"diagnostic_queries": 16, "model_calls": 60}, seed_obs,
        propose=_develop(SW_TASK, 5),
        charter={"objective": "x"},
        boundary={"world": 0, "arm": "I", "seq": 0},
        experience=experience, state=state,
        construction={"dsn": None, "cid": "probe", "gateway": None,
                      "model": "", "model_cap": 60, "budget": {}},
        journal={"dsn": None, "cid": None, "decision": None})
    sequenced = ResourceEnvelope.sequence_construction_allowance(
        REMAINING, observation["queries"])
    assert captured["max_queries"] == sequenced
    assert captured["max_queries"] <= REMAINING - 1 - observation[
        "queries"]
    assert spend <= REMAINING


def test_zero_budget_probe_consumes_no_study_lineage():
    from experiments.ad01 import trajectory as T
    probe = T.dev_episode(SW_TASK, "seed-sw-greedy", max_queries=0)
    assert probe["disposition"] == "no-candidate"
    assert probe["fallback"] == "incumbent"
    assert probe["lineage"] == []
    assert "zero-budget-probe" in probe["fallback_reason"]
    assert probe["queries"] == 0


def test_zero_allowance_boundary_makes_no_construction_call(
        monkeypatch):
    from experiments.ad01 import construct as C
    calls = []

    def fake_construct(dsn, *, campaign_id, task, experience, budget,
                       gateway, model):
        calls.append(dict(budget))
        raise AssertionError("zero-budget probe must not construct")

    monkeypatch.setattr(C, "construct_method", fake_construct)
    T, capability, seed_obs, experience, state = _boundary_args(
        GRAPH_TASK)
    observation, episode, spend = T._run_boundary(
        GRAPH_TASK, capability,
        {"diagnostic_queries": 16, "model_calls": 60}, seed_obs,
        propose=_develop(GRAPH_TASK, 0),
        charter={"objective": "x"},
        boundary={"world": 0, "arm": "I", "seq": 0},
        experience=experience, state=state,
        construction={"dsn": None, "cid": "probe", "gateway": None,
                      "model": "", "model_cap": 60, "budget": {}},
        journal={"dsn": None, "cid": None, "decision": None})
    assert calls == []
    assert episode["disposition"] == "no-candidate"
    assert episode["lineage"] == []
    assert episode["construction_calls"] == 0
    assert spend <= REMAINING
