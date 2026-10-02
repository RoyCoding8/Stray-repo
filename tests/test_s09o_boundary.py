"""Boundary regressions for the two exploits found by adversarial review of 8e05c14.

Both ran as demonstrated probes before these checks existed. The first copied a
sealed answer out of the runtime STEP view into a model prompt argument. The
second executed an unassessed fallback member under a promoting release while
the use record claimed the requested capability had executed.
"""

from experiments.ad01 import policy_step, selection

SECRET = "sealed-answer-probe-9f3c"


def _sealed_observation() -> dict:
    return {"observation_id": "obs-sealed-probe",
            "task_id": "ad01-w0-dev-sw-00",
            "capability_id": "seed-sw-greedy",
            "verdict": "preserved",
            "detail": {"access_label": "hidden", "sealed_answer": SECRET}}


def test_sealed_observation_absent_from_runtime_policy_view():
    view = policy_step.materialize_view(
        task={"task_id": "ad01-w0-dev-sw-00", "family": "software"},
        observations=[_sealed_observation()],
        open_questions=[], last_result=None,
        eligible_methods=[], remaining={"model_calls": 1})
    import json
    assert SECRET not in json.dumps(view, sort_keys=True)
    assert view["observations"] == []


def test_sealed_detail_key_dropped_but_legitimate_feedback_survives():
    sealed_key_obs = {"observation_id": "obs-sealed-key",
                      "task_id": "ad01-w0-dev-sw-00",
                      "capability_id": "seed-sw-greedy",
                      "verdict": "preserved",
                      "detail": {"hidden_answer": SECRET, "queries": 3}}
    legitimate = {"observation_id": "obs-visible",
                  "task_id": "ad01-w0-dev-sw-01",
                  "capability_id": "seed-sw-greedy",
                  "verdict": "rejected",
                  "detail": {"queries": 4, "reason": "size grew"}}
    view = policy_step.materialize_view(
        task={"task_id": "ad01-w0-dev-sw-00", "family": "software"},
        observations=[sealed_key_obs, legitimate], open_questions=[],
        last_result=None, eligible_methods=[], remaining={"model_calls": 1})
    import json
    assert SECRET not in json.dumps(view, sort_keys=True)
    surviving = view["observations"]
    assert [o["observation_id"] for o in surviving] == ["obs-visible"]
    assert surviving[0]["verdict"] == "rejected"
    assert surviving[0]["detail"]["reason"] == "size grew"


def test_promoting_release_refuses_unassessed_fallback():
    import hashlib
    assessed = "def assessed(task, oracle, max_queries=16):\n    return {}\n"
    assessed_digest = hashlib.sha256(assessed.encode()).hexdigest()
    repertoire = {
        "members": [{"capability_id": "seed-sw-greedy",
                     "method_source": "def unassessed(task, oracle):\n"
                                      "    return {}\n",
                     "source_digest": hashlib.sha256(
                         b"def unassessed(task, oracle):\n    return {}\n"
                         ).hexdigest(),
                     "scope": {"family": "software"}}],
        "active_binding": {"versions": ["absent-from-repertoire"],
                           "scope": {"family": "software"},
                           "disposition": "default",
                           "fallback": "seed-sw-greedy",
                           "invalidation": {
                               "candidate_digest": assessed_digest}}}
    chosen = selection.select_member(
        repertoire, {"family": "software"}, release_id="rel-under-test")
    assert chosen is None, (
        "a promoting release whose pinned bytes are absent must refuse,"
        " not execute an unassessed fallback")
    assert assessed_digest != repertoire["members"][0]["source_digest"]
