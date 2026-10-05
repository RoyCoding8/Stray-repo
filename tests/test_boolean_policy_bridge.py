"""The executable policy governs admitted Boolean-world actions."""

from __future__ import annotations

from experiments.ad01 import boolean_active as active
from experiments.ad01 import boolean_policy
from experiments.ad01 import policy_step
from experiments.ad01 import rule_learner


PROBE_THEN_COMMIT_SOURCE = '''def STEP(view, state):
    observed = view["observed"]
    if not observed:
        action = {
            "kind": "probe",
            "target": "boolean.query",
            "inputs": {"x": 3},
            "evidence_refs": [],
            "requested_resources": {"queries": 1},
        }
        return {"action": action, "state": {"probed": False}}
    observed_y = observed[-1]["y"]
    specs = [{"const": bit, "mask": 0, "pair": None} for bit in observed_y]
    commit_kind = view["action_schema"]["actions"].keys()
    commit_kind = [kind for kind in commit_kind if kind not in ("probe", "stop")][0]
    action = {
        "kind": commit_kind,
        "target": "boolean.commit",
        "inputs": {"specs": specs},
        "evidence_refs": [],
        "requested_resources": {},
    }
    return {"action": action, "state": {"probed": True}}
'''

STOP_SOURCE = '''def STEP(view, state):
    action = {
        "kind": "stop",
        "target": "boolean.task",
        "inputs": {},
        "evidence_refs": [],
        "requested_resources": {},
    }
    return {"action": action, "state": {}}
'''

MALFORMED_SOURCE = '''def STEP(view, state):
    action = {"kind": "teleport", "target": "boolean.task"}
    return {"action": action, "state": {}}
'''

ERROR_SOURCE = '''def STEP(view, state):
    raise RuntimeError("policy failed")
'''

REJECTED_STATE_SOURCE = '''def STEP(view, state):
    if not state:
        action = {
            "kind": "probe",
            "target": "boolean.query",
            "inputs": {"x": 99},
            "evidence_refs": [],
            "requested_resources": {"queries": 1},
        }
        return {"action": action, "state": {"step": "poisoned"}}
    action = {
        "kind": "stop",
        "target": "boolean.task",
        "inputs": {"received": state.get("step")},
        "evidence_refs": [],
        "requested_resources": {},
    }
    return {"action": action, "state": {}}
'''

TIMEOUT_SOURCE = '''def STEP(view, state):
    while True:
        pass
'''

HIDDEN_STATE_SOURCE = '''def STEP(view, state):
    hidden = view["tables"]
    action = {
        "kind": "stop",
        "target": "boolean.task",
        "inputs": {"hidden": hidden},
        "evidence_refs": [],
        "requested_resources": {},
    }
    return {"action": action, "state": {}}
'''

OVERSIZED_STATE_SOURCE = '''def STEP(view, state):
    action = {
        "kind": "stop",
        "target": "boolean.task",
        "inputs": {},
        "evidence_refs": [],
        "requested_resources": {},
    }
    return {"action": action, "state": {"data": "x" * 5000}}
'''


def _artifact(source: str) -> dict:
    return policy_step.make_policy_artifact(
        source, origin="authored-control", instruments=["boolean-rule-v1"])


def _run(source: str, **limits):
    return active.run_episode(
        boolean_policy.choose_action(_artifact(source), **limits),
        split="dev", seed=4)


def _frozen_r4_host_queries():
    task = active.rules.make_task("dev", 4)
    session = active.rules.RuleSession(task)
    learner = rule_learner.VersionSpaceLearner(active.rules.CLASS_TABLES, 4)
    queries = []
    while session.remaining > 0:
        pick = learner.choose_query(dict(session.queried))
        if pick is None:
            break
        queries.append(pick)
        learner.observe(pick, session.query(pick))
    remaining = iter(queries)

    def choose(_state):
        return active.as_shared_action({
            "kind": active.PROBE, "x": next(remaining), "specs": []})

    return choose


def _refusal(result: dict) -> dict:
    return result["trace"][-1]["action"]["inputs"]["bridge_refusal"]


def test_hand_written_policy_probes_x3_then_commits_and_is_scored():
    result = _run(PROBE_THEN_COMMIT_SOURCE)

    assert result["queried"] == [3]
    assert result["trace"][0]["action"]["inputs"] == {"x": 3}
    assert result["trace"][0]["effect"] == {
        "kind": "probe", "x": 3, "observation": (1, 0, 0, 1)}
    assert result["trace"][1]["action"]["kind"] == "construct"
    assert result["trace"][1]["action"]["inputs"]["specs"] == [
        {"const": 1, "mask": 0, "pair": None},
        {"const": 0, "mask": 0, "pair": None},
        {"const": 0, "mask": 0, "pair": None},
        {"const": 1, "mask": 0, "pair": None},
    ]
    assert result["trace"][1]["effect"] == {
        "kind": "commit", "committed": True}
    assert result["committed"] is True
    assert result["final"] == {
        "overall": 0.1875, "queried": 1.0,
        "unqueried": 0.13333333333333333, "n_queried": 1}


def test_the_frozen_r4_host_query_arrangement_scores_nothing():
    result = active.run_episode(
        _frozen_r4_host_queries(), split="dev", seed=4)

    # The arrangement is frozen because the host learner is now a total
    # order on (state, budget), so these literals are reproducible rather
    # than incidental. They previously read
    # [1, 2, 4, 7, 8, 13, 14, 15], which came from the seed-driven
    # random tie-break that `rule_learner` no longer has. What the test
    # is about is unchanged: a host that spends all eight queries on
    # probes and never commits scores nothing.
    assert result["queried"] == [0, 1, 2, 4, 7, 8, 11, 13]
    assert [step["action"]["inputs"]["x"]
            for step in result["trace"]] == [0, 1, 2, 4, 8, 7, 11, 13]
    assert result["trace"][-1]["state_before"] == {
        "remaining": 1, "queried": [0, 1, 2, 4, 7, 8, 11]}
    assert result["committed"] is False
    assert result["final"] is None


def test_a_malformed_policy_action_becomes_a_traceable_stop():
    result = _run(MALFORMED_SOURCE)

    assert result["trace"][-1]["action"]["kind"] == "stop"
    assert result["trace"][-1]["effect"] == {"kind": "stop", "remaining": 8}
    assert _refusal(result)["stage"] == "policy-step"
    assert "unknown action kind" in _refusal(result)["reason"]
    assert result["queried"] == []
    assert result["committed"] is False


def test_a_policy_error_becomes_a_traceable_stop():
    result = _run(ERROR_SOURCE)

    assert result["trace"][-1]["effect"] == {"kind": "stop", "remaining": 8}
    assert "RuntimeError: policy failed" in _refusal(result)["reason"]
    assert result["queried"] == []


def test_a_rejected_action_does_not_advance_policy_state():
    session = active.rules.RuleSession(active.rules.make_task("dev", 4))
    decide = boolean_policy.choose_action(_artifact(REJECTED_STATE_SOURCE))
    public_state = active.public_state(session)

    first = decide(public_state)
    second = decide(public_state)

    assert first["kind"] == "stop"
    assert first["inputs"]["bridge_refusal"]["reason"].startswith(
        "probe x must be an integer in 0..15")
    assert second == first


def test_a_policy_timeout_becomes_a_traceable_stop():
    result = _run(TIMEOUT_SOURCE, timeout_ms=25, cpu_seconds=1)

    assert result["trace"][-1]["effect"] == {"kind": "stop", "remaining": 8}
    assert _refusal(result)["reason"].startswith("timeout:")
    assert result["queried"] == []


def test_a_policy_cannot_read_the_hidden_tables():
    result = _run(HIDDEN_STATE_SOURCE)

    assert result["task_id"] == active.rules.make_task("dev", 4)["task_id"]
    assert "tables" in _refusal(result)["reason"]
    assert "KeyError" in _refusal(result)["reason"]
    assert result["trace"][-1]["effect"] == {"kind": "stop", "remaining": 8}
    assert result["queried"] == []


def test_the_shared_view_only_repackages_public_state():
    state = active.public_state(active.rules.RuleSession(
        active.rules.make_task("dev", 4)))
    view = boolean_policy._shared_view(state)

    assert set(view) == {
        "instrument", "task_id", "observed", "remaining", "public_world",
        "action_schema"}
    assert view["instrument"] == state["instrument"]
    assert view["task_id"] == state["task_id"]
    assert view["observed"] == state["observed"]
    assert view["remaining"] == state["remaining"]
    assert view["public_world"] == {
        "split": state["split"],
        "max_queries": state["max_queries"],
        "hypothesis_class": state["hypothesis_class"],
    }
    assert view["action_schema"]["actions"] == {
        "probe": state["action_schema"]["actions"]["probe"],
        "construct": state["action_schema"]["actions"]["commit"],
        "stop": state["action_schema"]["actions"]["stop"],
    }
    assert "tables" not in view
    assert "tables" not in view["public_world"]


def test_an_oversized_policy_state_becomes_a_traceable_stop():
    result = _run(OVERSIZED_STATE_SOURCE)

    assert result["trace"][-1]["effect"] == {"kind": "stop", "remaining": 8}
    assert "policy state exceeds 4096 bytes" in _refusal(result)["reason"]
    assert result["queried"] == []


def test_a_policy_can_stop_before_spending_a_query():
    result = _run(STOP_SOURCE)

    assert result["trace"] == [{
        "action": {
            "kind": "stop", "target": "boolean.task", "inputs": {},
            "evidence_refs": [], "requested_resources": {}},
        "effect": {"kind": "stop", "remaining": 8},
        "state_before": {"remaining": 8, "queried": []},
    }]
    assert result["queried"] == []
    assert result["committed"] is False
    assert result["final"] is None
