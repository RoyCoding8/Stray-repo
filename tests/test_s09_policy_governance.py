"""Does a bound STEP policy govern use, or only decorate a record?

Finding S09R-02 in `reviews/STAGE-09-GENERALITY-LIVE-REVIEW.md` claims a bound
policy digest was copied onto use records whose executed bytes were an authored
`ENTRY` constant. These tests recompute both columns from bytes on disk, then
try to break the claim two ways: substitute the policy with the method
repertoire held fixed, and disconnect the policy and demand a refusal.

Every digest here is recomputed. A test that reads a stored digest and asserts
it equals itself would pass if the evidence were deleted.
"""

from __future__ import annotations

import hashlib
import json
import os

import pytest

from experiments.ad01 import policy_action
from experiments.ad01 import policy_step
from experiments.ad01 import s09_policy_governance as gov
from execution_authority import execution_store as make_execution_store

TASK_ID = "ad01-w1-within-sw-00"

P1_BOUND_DIGEST = (
    "b71a7f8f39ad1655555f0ac47ab2ab81321a78d98ac90f1079944fc626194706")
AUTHORED_METHOD_DIGEST = (
    "3834317f66d4fb086d9e4cc93c36c0b08e4a108478dd26b776de66ea04c58685")


@pytest.fixture(scope="module")
def execution_store():
    with make_execution_store("ci-s09gov") as store:
        yield store


def _execution(store: dict, operation_id: str) -> dict:
    return {"dsn": store["dsn"],
            "allocation_id": store["allocation_id"],
            "operation_id": operation_id}


def _use_policy(method_id: str) -> str:
    return (
        "def STEP(view, state):\n"
        "    action = {'kind': 'use_method',\n"
        "              'target': view['task_content']['task_id'],\n"
        "              'inputs': {'method_id': '%s', 'max_queries': 16},\n"
        "              'evidence_refs': [],\n"
        "              'requested_resources': {'queries': 16}}\n"
        "    return {'action': action, 'state': {'chosen': '%s'}}\n"
        % (method_id, method_id))


def _bound(source: str, arm: str) -> gov.BoundPolicy:
    return gov.bind(source, arm=arm,
                    recorded_digest=hashlib.sha256(source.encode()).hexdigest(),
                    entry=policy_step.STEP_ENTRY, origin="authored-control",
                    source_path="tests/test_s09_policy_governance.py:%s" % arm,
                    disposition="test-fixture")


def _expected_action(method_id: str) -> dict:
    return {"kind": "use_method", "target": TASK_ID,
            "inputs": {"method_id": method_id, "max_queries": 16},
            "evidence_refs": [], "requested_resources": {"queries": 16}}


def test_the_operational_action_vocabulary_is_disjoint_from_the_shared_one():
    """The two action contracts cannot both admit a non-stop policy.

    `policy_action` is the shared six-kind representation contract and
    `policy_step` is the vocabulary the operational dispatcher executes. They
    share only `stop`, so a policy conforming to one is refused by the other
    unless it stops. A fixture that satisfied both is impossible.
    """
    for kind in policy_step.ACTION_KINDS:
        payload = {"kind": kind, "target": "ad01-w1-within-sw-00", "inputs": {},
                   "evidence_refs": [], "requested_resources": {}}
        if kind == "stop":
            assert policy_action.parse_action(payload).kind == "stop"
            continue
        with pytest.raises(policy_action.ActionRefused):
            policy_action.parse_action(payload)

    assert sorted(set(policy_action.ACTION_KINDS)
                  & set(policy_step.ACTION_KINDS)) == ["stop"]
    assert gov.OPERATIONAL_POLICY != gov.TASK_METHOD


def test_a_conforming_shared_action_is_refused_by_the_operational_dispatcher(
        execution_store):
    source = (
        "def STEP(view, state):\n"
        "    action = {'kind': 'use', 'target': view['task_content']['task_id'],\n"
        "              'inputs': {'method_id': 'seed-sw-greedy'},\n"
        "              'evidence_refs': [], 'requested_resources': {}}\n"
        "    return {'action': action, 'state': {}}\n")
    policy = _bound(source, "shared-shape")

    with pytest.raises(gov.GovernanceRefused) as refused:
        gov.run_episode(policy, TASK_ID,
                        **_execution(execution_store, "shared-action"))

    assert refused.value.stage == gov.REFUSAL_NO_STEP
    assert "unknown policy action kind: 'use'" in refused.value.reason


def test_binding_rehashes_the_bytes_and_refuses_a_digest_they_do_not_produce():
    source = _use_policy("seed-sw-greedy")

    bound = _bound(source, "greedy")
    assert bound.digest == hashlib.sha256(source.encode()).hexdigest()
    assert bound.digest != P1_BOUND_DIGEST

    with pytest.raises(gov.GovernanceRefused) as refused:
        gov.bind(source, arm="greedy", recorded_digest=P1_BOUND_DIGEST,
                 entry=policy_step.STEP_ENTRY, origin="authored-control",
                 source_path="tests", disposition="test-fixture")

    assert refused.value.stage == gov.REFUSAL_NO_STEP
    assert P1_BOUND_DIGEST in refused.value.reason
    assert bound.digest in refused.value.reason


def test_the_committed_bundle_policy_reloads_from_durable_bytes():
    policy = gov.load_bundle_policy("P1")

    assert policy.digest == P1_BOUND_DIGEST
    assert policy.digest == hashlib.sha256(policy.source.encode()).hexdigest()
    assert policy.digest == policy.recorded_digest
    assert policy.as_dict()["digest_matches_record"] is True
    assert policy.entry == policy_step.STEP_ENTRY
    assert "def STEP(view, state):" in policy.source


def test_the_bundle_policy_is_bound_but_never_released():
    policy = gov.load_bundle_policy("P1")

    assert policy.disposition == "bound"
    assert policy.release_id.startswith("ad01-ad01-w0-I-54-policy-")
    assert policy.released is False
    assert policy.column == gov.OPERATIONAL_POLICY


def test_a_policy_with_an_unrecognized_origin_is_refused():
    source = _use_policy("seed-sw-greedy")

    with pytest.raises(gov.GovernanceRefused) as refused:
        gov.bind(source, arm="greedy",
                 recorded_digest=hashlib.sha256(source.encode()).hexdigest(),
                 entry=policy_step.STEP_ENTRY, origin="copied-off-a-record",
                 source_path="tests", disposition="test-fixture")

    assert refused.value.stage == gov.REFUSAL_NO_STEP
    assert "unknown policy origin 'copied-off-a-record'" in refused.value.reason


def test_a_fresh_interpreter_executes_the_bound_bytes_not_the_digest(
        execution_store):
    policy = _bound(_use_policy("seed-sw-greedy"), "greedy")

    episode = gov.run_episode(
        policy, TASK_ID, **_execution(execution_store, "fresh-bytes"))

    assert episode.fresh_process is True
    assert episode.episode_pid != os.getpid()
    assert episode.driver_pid == os.getpid()
    assert episode.admitted[0].executed_digest == policy.digest
    assert episode.admitted[0].launcher == "local-process"
    assert episode.admitted[0].wall_ms > 0
    assert any(part.endswith("driver.py")
               for part in episode.admitted[0].argv)
    assert episode.admitted[0].action == _expected_action("seed-sw-greedy")
    assert execution_store["dsn"] not in json.dumps(episode.as_dict())


def test_substituting_the_policy_with_the_repertoire_fixed_moves_the_outcome(
        execution_store):
    greedy = _bound(_use_policy("seed-sw-greedy"), "greedy")
    ddmin = _bound(_use_policy("seed-sw-ddmin"), "ddmin")

    verdict = gov.substitution_verdict(
        greedy, ddmin, TASK_ID, dsn=execution_store["dsn"],
        allocation_id=execution_store["allocation_id"],
        operation_id="substitution")

    assert verdict["repertoire_held_fixed"] == [
        "seed-sw-ddmin", "seed-sw-greedy", "seed-gr-ddmin", "seed-gr-greedy"]
    assert verdict["views_identical"] is True
    assert verdict["admitted_sequences"]["first"] == [
        gov._canonical(_expected_action("seed-sw-greedy"))]
    assert verdict["admitted_sequences"]["second"] == [
        gov._canonical(_expected_action("seed-sw-ddmin"))]
    assert verdict["admitted_sequence_differs"] is True
    assert verdict["executed_identities"] == {
        "first": ["seed-sw-greedy"], "second": ["seed-sw-ddmin"]}
    assert verdict["executed_owners"] == {
        "first": ["seeds.run_seed"], "second": ["seeds.run_seed"]}
    assert verdict["executed_identity_differs"] is True
    assert verdict["policy_governs"] is True


def test_the_same_policy_replays_the_same_admitted_sequence(execution_store):
    policy = _bound(_use_policy("seed-sw-greedy"), "greedy")

    first = gov.run_episode(
        policy, TASK_ID, **_execution(execution_store, "replay-first"))
    second = gov.run_episode(
        policy, TASK_ID, **_execution(execution_store, "replay-second"))

    assert first.admitted_sequence == second.admitted_sequence
    assert [m.identity for m in first.methods] == [
        m.identity for m in second.methods]
    assert first.view_digest == second.view_digest
    assert first.episode_pid != second.episode_pid


def test_the_two_artifact_columns_name_different_digests_in_the_bundle():
    verdict = gov.bundle_method_governs("P1")

    assert verdict["policy_digest"] == P1_BOUND_DIGEST
    assert verdict["authored_method_digest"] == AUTHORED_METHOD_DIGEST
    assert verdict["authored_method_digest"] == hashlib.sha256(
        gov.pilot_method_source().encode("utf-8")).hexdigest()
    assert verdict["policy_digest_equals_executed_digest"] is False
    assert verdict["governing_column"] == gov.TASK_METHOD
    assert verdict["use_records_executing_authored_method"] == 4
    assert verdict["record_digests_match_recomputed"] is True


def test_the_task_method_column_names_the_reducer_that_actually_ran(
        execution_store):
    policy = _bound(_use_policy("seed-sw-greedy"), "greedy")

    episode = gov.run_episode(
        policy, TASK_ID, **_execution(execution_store, "method-column"))
    method = episode.methods[0]

    assert method.column == gov.TASK_METHOD
    assert method.identity == "seed-sw-greedy"
    assert method.owner == "seeds.run_seed"
    assert method.queries == 12
    assert method.outcome_digest == hashlib.sha256(
        json.dumps(method.outcome, sort_keys=True, separators=(",", ":")
                   ).encode("utf-8")).hexdigest()
    assert method.outcome["family"] == "software"
    assert method.outcome["fault"] == "stale-read"
    assert not hasattr(method, "governed_by_policy")


def test_connected_episode_requires_authority_before_outer_dispatch(
        monkeypatch):
    from settlement.launcher_local import LocalLauncher

    def fail_if_dispatched(*args, **kwargs):
        raise AssertionError("uncredentialed episode reached outer dispatch")

    monkeypatch.setattr(LocalLauncher, "dispatch", fail_if_dispatched)
    policy = _bound(_use_policy("seed-sw-greedy"), "greedy")
    for authority in ({},
                      {"dsn": "test-store"},
                      {"dsn": "test-store", "allocation_id": "test-allocation"}):
        with pytest.raises(gov.GovernanceRefused) as refused:
            gov.run_episode(policy, TASK_ID, **authority)
        assert refused.value.stage == gov.REFUSAL_NO_STEP
        assert "explicit caller store, allocation, and operation" in (
            refused.value.reason)


def test_the_episode_refuses_when_the_policy_dispatcher_is_absent(
        monkeypatch):
    from settlement.launcher_local import LocalLauncher

    def fail_if_dispatched(*args, **kwargs):
        raise AssertionError("disconnected episode reached outer dispatch")

    monkeypatch.setattr(LocalLauncher, "dispatch", fail_if_dispatched)
    policy = _bound(_use_policy("seed-sw-greedy"), "greedy")

    with pytest.raises(gov.GovernanceRefused) as refused:
        gov.run_episode(policy, TASK_ID, dispatcher=None)

    assert refused.value.stage == gov.REFUSAL_NO_DISPATCHER
    assert "no policy dispatcher" in refused.value.reason


def test_the_disconnect_countercheck_reports_its_own_refusal_loudly(
        execution_store):
    policy = _bound(_use_policy("seed-sw-greedy"), "greedy")

    verdict = gov.disconnect_verdict(
        policy, TASK_ID, dsn=execution_store["dsn"],
        allocation_id=execution_store["allocation_id"],
        operation_id="disconnect")

    assert verdict["no_dispatcher"] == {
        "stage": gov.REFUSAL_NO_DISPATCHER,
        "reason": "use was attempted with no policy dispatcher"}
    assert verdict["refused_without_dispatcher"] is True
    assert verdict["unnamed_method_action"] == {
        "kind": "use_method", "inputs": {}}


def test_the_disconnect_countercheck_reports_the_pipeline_silent_fallback():
    # RED until `assessment_profile._resolve_method` refuses a `use_method`
    # action that names no method instead of defaulting to seed-<family>-greedy.
    # The repair is in a file this lane does not own, so the test stays red.
    policy = _bound(_use_policy("seed-sw-greedy"), "greedy")

    verdict = gov.disconnect_verdict(policy, TASK_ID)

    assert verdict["unnamed_method_effect"]["accepted"] is False
    assert verdict["unnamed_method_effect"]["selected_identity"] is None
    assert verdict["reached_repertoire_without_policy"] is False


def test_a_bundle_without_a_construction_response_refuses_rather_than_defaulting():
    with pytest.raises(gov.GovernanceRefused) as refused:
        gov.load_bundle_policy("P1", bundle=gov.ROOT / "experiments" / "ad01")

    assert refused.value.stage == gov.REFUSAL_NO_STEP
    assert "no construction response" in refused.value.reason

    with pytest.raises(gov.GovernanceRefused) as absent:
        gov.load_bundle_policy("P9")

    assert absent.value.stage == gov.REFUSAL_NO_STEP
    assert "no arm 'P9'" in absent.value.reason
