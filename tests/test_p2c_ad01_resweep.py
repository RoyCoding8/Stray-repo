"""Pass-2 resweep (AD01): spend accounting, store-data guards, diagnostic refusal.

Regression pins for fresh-angle bugs found after pass 1:
- development success spend dropped the diagnostic observation queries,
  so campaign witness queries disagreed with the trajectory query cap;
- asserts on settlement-store data crashed the live path instead of
  refusing with a controlled error;
- a model-derived family-mismatched (or unknown-target) diagnostic
  crashed run_diagnostic with a bare assert instead of a refusal.
"""

from __future__ import annotations

import pytest

from experiments.ad01 import construct as _construct
from experiments.ad01 import seeds
from experiments.ad01 import trajectory
from experiments.ad01 import worlds
from experiments.ad01.learner import LearnerRefused
from settlement.common import SettlementError

from tests.conftest_isolation import admin_dsn, dsn_with_dbname

# A store that must stay absent: these tests assert a refusal, and creating
# the database would invert them. What has to be real is the route, because the
# refusal is raised only after the read that finds no boundary row. The
# route resolves at call time -- an import-time binding would raise on a
# routeless session and kill collection of the whole suite.


def _unused_dsn() -> str:
    return dsn_with_dbname(admin_dsn(), "ec02test_p2c_unused")

GRAPH_TASK = "ad01-w0-dev-gr-00"


def _seed_result():
    task = worlds.load_task(worlds.FROZEN_DIR, GRAPH_TASK)
    capability = next(
        c for c in seeds.SEED_CAPABILITIES
        if c["capability_id"] == "seed-gr-greedy")
    return seeds.run_seed(capability, task, max_queries=8)


def test_dev_success_spend_counts_diagnostic_queries(monkeypatch):
    res = _seed_result()
    assert res["queries"] > 0

    def fake_propose(seen, asked):
        seed_obs = seen["observations"][-1]
        return {"basis_references": [seed_obs["observation_id"]],
                "question": "q",
                "next_action": {"kind": "development",
                                "diagnostic": "graph",
                                "task_id": GRAPH_TASK,
                                "max_queries": 8},
                "requested_resources": {"diagnostic_queries": 1}}

    def fake_diagnostic(admitted, seen, budget=None):
        return {"observation_id": "obs-fake-1", "task_id": GRAPH_TASK,
                "verdict": "v", "queries": 8, "detail": {}}

    def fake_construct(dsn, *, campaign_id, task, experience, budget,
                       gateway, model):
        return {"capability_id": "acquired-gr-fake",
                "method_source": "src", "entry": "ENTRY",
                "source_digest": "d", "authored": False,
                "scope": {"family": "graph"},
                "lineage": {"calls_made": 2},
                "validation": {"result": {"candidate": res["candidate"],
                                          "queries": res["queries"]}}}

    monkeypatch.setattr(trajectory, "run_diagnostic", fake_diagnostic)
    monkeypatch.setattr(_construct, "construct_method", fake_construct)
    monkeypatch.setattr(
        trajectory, "bind_method_release",
        lambda *args, **kwargs: {"bound": False,
                                 "reason": "release persistence is outside this test"})
    caps = {"diagnostic_queries": 16, "model_calls": 60}
    seed_obs = {"observation_id": "obs-seed", "task_id": GRAPH_TASK,
                "capability_id": "seed-gr-greedy", "verdict": "unmeasured"}
    state = {"dev_episodes": 0, "model_calls": 0, "construction_calls": 0}
    experience = {"observations": [], "retained": [],
                  "remaining": {"queries": 16, "boundaries": 6,
                                "dev_episodes": 3, "model_calls": 60}}
    construction = {"dsn": "none", "cid": "c", "gateway": None,
                    "model": "m", "model_cap": 60, "budget": {}}
    _obs, episode, spend = trajectory._run_boundary(
        GRAPH_TASK, "seed-gr-greedy", caps, seed_obs, propose=fake_propose,
        charter={"objective": "x"},
        boundary={"world": 0, "arm": "I", "seq": 0},
        experience=experience, state=state, construction=construction,
        journal={"dsn": None, "cid": "c", "decision": None})
    assert episode["queries"] == 8 + res["queries"]
    assert spend == 1 + 8 + res["queries"]


class _Made:
    def __init__(self, attempt_id):
        self.data = {"attempt_id": attempt_id}


def _no_settled_read(monkeypatch):
    """Stop the trajectory reading the absent database before a guard fires.

    `UNUSED_DSN`'s database must stay absent -- these tests assert a refusal and
    creating it would invert them -- so a real read of it raises
    `OperationalError` before the guard under test is reached. Two of them do.
    `resume_campaign` reads at `trajectory.py:36` through `_settled_attempts`
    before `run_campaign` is called, which is why stubbing `run_campaign` alone
    did not stop the connect. `_publish_boundary` reads through
    `_s09_effect_id` -> `_s09_get` -> `_read_conn` at `:1540` before its store
    calls, which is why stubbing `acquire_work` alone did not stop it either.

    Both stubs answer the question the caller actually asks -- is there a
    settled attempt, is there an effect id -- with "no", which is the state an
    unused database is in by definition. The dbname stays the absent one the
    assertion depends on; what changes is that nothing reads it.
    """
    monkeypatch.setattr(trajectory, "_settled_attempts", lambda dsn, cid: [])
    monkeypatch.setattr(trajectory, "_s09_effect_id", lambda dsn, cid, seq: None)


def test_record_decision_store_mismatch_refuses(monkeypatch):
    import settlement.store as _store
    monkeypatch.setattr(_store, "acquire_work",
                        lambda dsn, cmd: _Made("att-ad01-w0-I-00-0"))
    monkeypatch.setattr(_store, "submit_observation",
                        lambda dsn, cmd: _Made("att-someone-else-9"))
    with pytest.raises(SettlementError):
        trajectory.record_decision(_unused_dsn(), "ad01-w0-I-00",
                                   0, {"next_action": {"kind": "stop"}})


def test_publish_boundary_store_mismatch_refuses(monkeypatch):
    _no_settled_read(monkeypatch)
    import settlement.store as _store
    monkeypatch.setattr(_store, "acquire_work",
                        lambda dsn, cmd: _Made("att-ad01-w0-I-00-0"))
    monkeypatch.setattr(_store, "submit_observation",
                        lambda dsn, cmd: _Made("att-someone-else-9"))
    with pytest.raises(SettlementError):
        trajectory._publish_boundary(
            _unused_dsn(), "ad01-w0-I-00", 0, GRAPH_TASK,
            decision=None, observation={"observation_id": "obs-1"},
            episode={}, spend=1)


def test_resume_campaign_id_mismatch_refuses_without_database_access(monkeypatch):
    _no_settled_read(monkeypatch)
    from experiments.ad01 import mission
    monkeypatch.setattr(mission, "resume_operation", lambda dsn, cid: [])
    monkeypatch.setattr(trajectory, "run_campaign",
                        lambda *a, **k: {"campaign_id": "ad01-w0-I-99"})
    with pytest.raises(ValueError, match="unexpected campaign"):
        trajectory.resume_campaign("unused-test-dsn", "ad01-w0-I-00",
                                   {"objective": "x"}, {})


def test_run_diagnostic_family_mismatch_refuses():
    admitted = {"basis_references": [], "question": "q",
                "next_action": {"kind": "diagnostic",
                                "diagnostic": "software",
                                "task_id": GRAPH_TASK},
                "requested_resources": {}}
    with pytest.raises(LearnerRefused, match="mismatches"):
        trajectory.run_diagnostic(admitted, {"observations": []}, budget=4)


def test_run_diagnostic_unknown_target_refuses():
    admitted = {"basis_references": [], "question": "q",
                "next_action": {"kind": "diagnostic",
                                "diagnostic": "software",
                                "task_id": "ad01-w9-dev-sw-99"},
                "requested_resources": {}}
    with pytest.raises(LearnerRefused, match="unknown diagnostic target"):
        trajectory.run_diagnostic(admitted, {"observations": []}, budget=4)
