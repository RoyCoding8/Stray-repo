from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_exhausted_durable_correction_returns_before_restarted_proposal(monkeypatch):
    from settlement import loop

    durable = {}

    def correction_state(dsn, study_root, decision_key):
        return dict(durable.get(decision_key, {"used": 0, "failure": {}}))

    def take_correction(dsn, study_root, decision_key, failure, attempt, budget):
        current = correction_state(dsn, study_root, decision_key)
        used = current["used"]
        if used >= budget:
            durable[decision_key] = {"used": used, "failure": dict(failure)}
            return {"allowed": False}
        durable[decision_key] = {"used": used + 1, "failure": dict(failure)}
        return {"allowed": True}

    monkeypatch.setattr(
        loop._authority, "corrections_total",
        lambda dsn, study_root: sum(row["used"] for row in durable.values()))
    monkeypatch.setattr(loop._authority, "correction_state", correction_state)
    monkeypatch.setattr(loop._authority, "take_correction", take_correction)
    monkeypatch.setattr(
        loop.ExperienceTransition, "read_journal",
        staticmethod(lambda *args, **kwargs: []))
    monkeypatch.setattr(
        loop.ExperienceTransition, "journal",
        lambda *args, **kwargs: None)
    calls = []

    def propose(materialized, state):
        calls.append((materialized["packet_id"], state.last_failure))
        return {"target": "t1", "instrument": "teleport", "inputs": {},
                "dependencies": [], "requested": {}}

    packet = {
        "packet_version": loop.PACKET_VERSION,
        "charter": {"objective": "x", "freeze_id": "ad01"},
        "visible_opportunities": ["t1"],
        "observations": [{"observation_id": "obs-0"}],
        "remaining": {"queries": 1, "model_calls": 1},
        "required_response": {"fields": ["answer"]},
    }
    first, _state = loop.run_boundary(
        "unused", study_root="study-restart", allocation_id="study-restart",
        packet=packet, propose=propose, max_corrections=1)
    decision_key = next(iter(durable))
    assert durable[decision_key]["used"] == 1
    assert first.admission == "refused:malformed-action"
    assert first.continuation["correction"] == "correction-budget-exhausted"
    assert len(calls) == 2

    restarted, _state = loop.run_boundary(
        "unused", study_root="study-restart", allocation_id="study-restart",
        packet=packet, propose=propose, max_corrections=1)

    assert restarted.admission == "refused:malformed-action"
    assert restarted.continuation == {
        "pending": [],
        "correction": "correction-budget-exhausted",
    }
    assert restarted.proposal["error"] == \
        durable[decision_key]["failure"]["reason"]
    assert len(calls) == 2
