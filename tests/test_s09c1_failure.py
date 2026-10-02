from __future__ import annotations

import pytest


def test_prior_state_read_failure_is_not_reset(monkeypatch):
    from experiments.ad01 import policy_step

    def fail(*args, **kwargs):
        raise RuntimeError("state store unavailable")

    monkeypatch.setattr(policy_step, "load_policy_state", fail)
    with pytest.raises(RuntimeError, match="state store unavailable"):
        policy_step.load_prior_final_state("dsn", "cid", 1)


def test_model_count_read_failure_is_not_zero(monkeypatch):
    from experiments.ad01 import policy_step, trajectory

    def fail(*args, **kwargs):
        raise RuntimeError("count store unavailable")

    monkeypatch.setattr(trajectory, "_read_conn", fail)
    with pytest.raises(RuntimeError, match="count store unavailable"):
        policy_step.durable_model_calls("dsn", "cid", 0)


def test_cached_step_source_mismatch_is_rejected():
    from experiments.ad01.agenda_policy import _cached_policy_decision

    cached = {"policy_output": {"source_digest": "old",
                                 "results": [{"action": {}}]},
              "accepted_action": {"next_action": {"kind": "stop"}}}
    with pytest.raises(ValueError, match="source digest mismatch"):
        _cached_policy_decision(cached, "new")
