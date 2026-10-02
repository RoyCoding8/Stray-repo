"""A use episode runs the method a policy admitted, or refuses.

The use phase used to take no policy at all: `run_use` selected a
repertoire member on its own and the caller stamped a policy digest onto
the record afterwards. A digest written after execution labels a run; it
does not govern it. These tests hold the fix in place by calling `run_use`
the way a user does.

The assertions name a literal capability id. A test that accepted any
truthy return would still pass if every method stopped running.
"""

from __future__ import annotations

import pytest

from experiments.ad01 import trajectory

TASK_ID = "ad01-w0-within-sw-00"
GRAPH_TASK_ID = "ad01-w0-transfer-gr-00"
CAMPAIGN = "ad01-w0-I-00"

GREEDY = "seed-sw-greedy"
DDMIN = "seed-sw-ddmin"

# `use_episode(None)` in `s09_bound_use_proof` is the pre-repair shape this
# module replaced: a consumer consulted before the episode and a synthetic
# record built on refusal. A callable is the contract `run_use` now takes.
POLICY_PREFIX = (
    "def policy(view, state):\n"
    "    return {'action': {'kind': 'use_method',\n"
    "                      'target': view['task_content']['task_id'],\n"
    "                      'inputs': {'method_id': %r, 'max_queries': 16},\n"
    "                      'evidence_refs': [],\n"
    "                      'requested_resources': {'queries': 16}},\n"
    "            'state': {'chosen': %r}}\n"
)


def naming(method_id: str, *, kind: str = "use_method", method: bool = True):
    source = POLICY_PREFIX % (method_id, method_id)
    source = source.replace("'use_method'", repr(kind), 1)
    if not method:
        source = source.replace("'max_queries': 16", "'max_queries': 16")
        source = source.replace("{'method_id': '', ", "{")
    namespace: dict = {}
    exec(source, namespace)
    return namespace["policy"]


def repertoire(*capability_ids: str) -> dict:
    return {
        "campaign_id": CAMPAIGN, "queries": 0,
        "members": [{"capability_id": capability_id,
                     "family": "software",
                     "scope": {"family": "software"},
                     "entry": "ENTRY", "authored": False}
                    for capability_id in capability_ids],
    }


def refusing(reason: str = "policy dispatcher unavailable"):
    """A dispatcher in the shape `agenda_policy.step_policy_consumer` returns."""
    seen: list = []

    class _Refusing:
        def decide(self, packet, state, *, boundary, experience):
            seen.append(packet)
            return {"status": "refused", "reason": reason, "corrections": 0}

    consumer = _Refusing()
    consumer.calls = seen
    return consumer


def test_the_policy_decides_which_method_runs():
    fixed = repertoire(GREEDY, DDMIN)

    [greedy] = trajectory.run_use(
        fixed, 0, "I", [TASK_ID], {}, policy=naming(GREEDY))
    [ddmin] = trajectory.run_use(
        fixed, 0, "I", [TASK_ID], {}, policy=naming(DDMIN))

    assert greedy["selected"] == GREEDY
    assert greedy["executed"] == GREEDY
    assert greedy["fallback_reason"] == ""
    assert ddmin["selected"] == DDMIN
    assert ddmin["executed"] == DDMIN
    assert ddmin["fallback_reason"] == ""


def test_an_admitted_method_runs_even_when_it_is_not_the_first_repertoire_member(
        ):
    """Selection used to take the first family match, policy or no policy."""
    reversed_order = repertoire(DDMIN, GREEDY)

    [record] = trajectory.run_use(
        reversed_order, 0, "I", [TASK_ID], {}, policy=naming(GREEDY))

    assert record["selected"] == GREEDY


def test_the_policy_admitted_action_carries_the_query_budget():
    source = (
        "def policy(view, state):\n"
        "    return {'action': {'kind': 'use_method',\n"
        "                      'target': view['task_content']['task_id'],\n"
        "                      'inputs': {'method_id': 'seed-sw-greedy',\n"
        "                                 'max_queries': 3},\n"
        "                      'evidence_refs': [],\n"
        "                      'requested_resources': {'queries': 3}},\n"
        "            'state': {}}\n")
    namespace: dict = {}
    exec(source, namespace)

    [record] = trajectory.run_use(
        repertoire(GREEDY), 0, "I", [TASK_ID], {},
        policy=namespace["policy"])

    assert record["costs"]["witness_queries"] <= 3


def test_a_use_episode_with_no_policy_refuses_and_runs_nothing():
    """The defect: no policy in hand used to mean `seed-<family>-greedy`."""
    [record] = trajectory.run_use(repertoire(GREEDY, DDMIN), 0, "I",
                                  [TASK_ID], {})

    assert record["status"] == "refused"
    assert record["selected"] == "refused"
    assert record["executed"] == "refused"
    assert record["executed_source"] == "refused"
    assert record["output"] == {}
    assert record["operation_ids"] == []
    assert record["costs"]["witness_queries"] == 0
    assert record["normalized_reduction"] == 0.0
    assert "no policy" in record["fallback_reason"]


def test_a_refusing_dispatcher_refuses_and_runs_nothing():
    consumer = refusing()

    [record] = trajectory.run_use(
        repertoire(GREEDY), 0, "I", [TASK_ID], {}, policy=consumer)

    assert record["status"] == "refused"
    assert record["executed"] == "refused"
    assert record["output"] == {}
    assert record["operation_ids"] == []
    assert record["costs"]["witness_queries"] == 0
    assert "policy dispatcher unavailable" in record["fallback_reason"]


def test_a_refusal_is_not_the_incumbent_an_empty_repertoire_produces():
    [refused] = trajectory.run_use(repertoire(GREEDY), 0, "I", [TASK_ID], {})

    assert refused["selected"] != "incumbent"
    assert refused["executed"] != "incumbent"
    assert refused["status"] == "refused"
    assert refused["output"] == {}
    assert refused["normalized_reduction"] == 0.0


def test_a_use_method_action_naming_no_method_refuses():
    [record] = trajectory.run_use(
        repertoire(GREEDY), 0, "I", [TASK_ID], {},
        policy=naming("", method=False))

    assert record["status"] == "refused"
    assert record["executed"] == "refused"
    assert "names no method" in record["fallback_reason"]


@pytest.mark.parametrize("kind", ["stop", "diagnose", "construct_method"])
def test_an_admitted_action_that_runs_no_method_refuses(kind):
    [record] = trajectory.run_use(
        repertoire(GREEDY), 0, "I", [TASK_ID], {},
        policy=naming(GREEDY, kind=kind))

    assert record["status"] == "refused"
    assert record["executed"] == "refused"
    assert "runs no task method" in record["fallback_reason"]


def test_a_method_the_repertoire_does_not_hold_refuses():
    [record] = trajectory.run_use(
        repertoire(GREEDY), 0, "I", [TASK_ID], {}, policy=naming(DDMIN))

    assert record["status"] == "refused"
    assert record["executed"] == "refused"
    assert DDMIN in record["fallback_reason"]


def test_one_refused_task_does_not_stop_the_others():
    consumer = refusing()
    consumer.decide = lambda packet, state, *, boundary, experience: (
        {"status": "refused", "reason": "gone", "corrections": 0}
        if packet["observations"][0]["task_id"] == TASK_ID
        else {"action": {"kind": "use_method",
                         "target": packet["observations"][0]["task_id"],
                         "inputs": {"method_id": GREEDY, "max_queries": 16},
                         "evidence_refs": [],
                         "requested_resources": {"queries": 16}}})

    records = trajectory.run_use(
        repertoire(GREEDY), 0, "I", [TASK_ID, "ad01-w0-transfer-sw-00"], {},
        policy=consumer)

    assert [r["executed"] for r in records] == ["refused", GREEDY]


def test_a_method_for_another_family_is_refused_rather_than_substituted():
    """A software capability cannot answer a graph task."""
    [record] = trajectory.run_use(
        repertoire(GREEDY), 0, "I", [GRAPH_TASK_ID], {},
        policy=naming(GREEDY))

    assert record["status"] == "refused"
    assert record["executed"] == "refused"


def test_a_policy_returning_a_malformed_action_refuses():
    source = (
        "def policy(view, state):\n"
        "    return {'action': {'kind': 'use_method'}, 'state': {}}\n")
    namespace: dict = {}
    exec(source, namespace)

    [record] = trajectory.run_use(
        repertoire(GREEDY), 0, "I", [TASK_ID], {},
        policy=namespace["policy"])

    assert record["status"] == "refused"
    assert record["executed"] == "refused"
    assert "missing" in record["fallback_reason"]


def test_a_policy_returning_an_untyped_action_refuses():
    namespace: dict = {}
    exec("def policy(view, state):\n    return {'action': 'use_method',"
         " 'state': {}}\n", namespace)

    [record] = trajectory.run_use(
        repertoire(GREEDY), 0, "I", [TASK_ID], {},
        policy=namespace["policy"])

    assert record["status"] == "refused"
    assert record["executed"] == "refused"


def test_use_refuses_a_task_no_policy_would_recognise():
    """Task admission is unchanged, and still raises."""
    with pytest.raises(ValueError, match="unknown task"):
        trajectory.run_use(repertoire(GREEDY), 0, "I", ["not-a-task"], {},
                           policy=naming(GREEDY))


def test_a_real_decision_consumer_is_refused_not_guessed_at():
    """`agenda_policy`'s consumer answers with an investigation, not an action.

    It has no vocabulary for naming a repertoire member, so there is
    nothing to admit. Reading one out of it would be the guess this lane
    removed; refusing keeps the gap visible at the boundary.
    """
    from experiments.ad01 import agenda_policy, policy_step
    from experiments.ad01 import s09_bound_use_proof as proof

    source = proof.seed_policy_source(GREEDY)
    artifact = policy_step.make_policy_artifact(
        source, origin="fixture-stand-in")["artifact"]
    consumer = agenda_policy.step_policy_consumer(
        {"artifact": artifact, "source_digest": artifact["source_digest"],
         "entry": "STEP", "policy_source": source},
        dsn=None, cid=CAMPAIGN)

    [record] = trajectory.run_use(
        proof.use_repertoire(), 1, "I", [proof.TASK_ID], {},
        policy=consumer)

    assert record["status"] == "refused"
    assert record["executed"] == "refused"
    assert "no valid action" in record["fallback_reason"]


def test_a_disconnected_decision_consumer_refuses_with_its_own_reason():
    """The disconnect S09R-02 asked for, reached through `run_use` itself."""
    from experiments.ad01 import agenda_policy, policy_step
    from experiments.ad01 import s09_bound_use_proof as proof

    source = proof.seed_policy_source(GREEDY)
    artifact = policy_step.make_policy_artifact(
        source, origin="fixture-stand-in")["artifact"]
    consumer = agenda_policy.step_policy_consumer(
        {"artifact": artifact, "source_digest": artifact["source_digest"],
         "entry": "STEP", "policy_source": source},
        dsn=None, cid=CAMPAIGN)
    consumer._disconnected = "policy dispatcher unavailable"

    [record] = trajectory.run_use(
        proof.use_repertoire(), 1, "I", [proof.TASK_ID], {},
        policy=consumer)

    assert record["status"] == "refused"
    assert record["executed"] == "refused"
    assert record["output"] == {}
    assert "policy dispatcher unavailable" in record["fallback_reason"]


def test_a_step_source_executed_out_of_process_runs_and_honours_its_budget():
    """The shipped `STEP` ABI, from source bytes, not a test double.

    `seed_policy_source` is the fixture the governance module also runs, so
    this covers the same bytes a bound policy would carry.
    """
    from experiments.ad01 import s09_bound_use_proof as proof

    namespace: dict = {}
    exec(proof.seed_policy_source(GREEDY), namespace)

    [record] = trajectory.run_use(
        proof.use_repertoire(), 1, "I", [proof.TASK_ID], {},
        policy=namespace["STEP"])

    assert record["selected"] == GREEDY
    assert record["executed"] == GREEDY
    assert record["fallback_reason"] == ""
    # the fixture asks for max_queries 4, not the repertoire default of 16
    assert record["costs"]["witness_queries"] == 4
    assert record["verdict"] == "preserved"

