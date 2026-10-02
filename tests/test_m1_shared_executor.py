"""M1 one runtime meaning: development and assessment share one dispatcher.

The legacy sealed assessor (policy_assess._effect) refuses model requests
and revision actions outright and resolves methods through its own branch,
while the operational STEP consumer admits them through broker effects.
That divergence is documented here under the labeled legacy profile.
New qualification routes both profiles through assessment_profile.dispatch,
which calls the same owners (broker-validated model ops, method_exec child,
seeds repertoire) with different declared permissions, visibility, budgets
and destinations.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from experiments.ad01 import (construct, policy_assess, policy_step, records,
                                seeds, trajectory, worlds)
from experiments.ad01.assessment_profile import (
    ASSESSMENT,
    ASSESSMENT_RESTRICTED,
    AUDIT,
    DEVELOPMENT,
    PROFILES,
    bind_revision,
    build_model_operation,
    dispatch,
    make_ctx,
)
from settlement import broker

TASK_ID = "ad01-w0-dev-sw-00"


def _task():
    return worlds.load_task(worlds.FROZEN_DIR, TASK_ID)


def _record(source):
    return policy_step.make_policy_artifact(source, origin="authored-control")


def _digest(source):
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


USE_SOURCE = (
    "def STEP(view, state):\n"
    "    target = view['task_content']['task_id']\n"
    "    action = {'kind': 'use_method', 'target': target,\n"
    "              'inputs': {'method_id': 'seed-sw-greedy',\n"
    "                         'max_queries': 4},\n"
    "              'evidence_refs': [],\n"
    "              'requested_resources': {'queries': 4}}\n"
    "    return {'action': action, 'state': {'done': True}}\n"
)


def _use_action(method_id="seed-sw-greedy", refs=()):
    return {"kind": "use_method", "target": TASK_ID,
            "inputs": {"method_id": method_id, "max_queries": 4},
            "evidence_refs": list(refs),
            "requested_resources": {"queries": 4}}


def _model_action(prompt="why does this reduction preserve the witness"):
    return {"kind": "request_model", "target": TASK_ID,
            "inputs": {"prompt": prompt, "max_output_tokens": 64},
            "evidence_refs": [],
            "requested_resources": {"model_calls": 1}}


def _revision_action():
    return {"kind": "propose_revision", "target": TASK_ID,
            "inputs": {"motivation": "try greedy first",
                       "scope": {"family": "software"}},
            "evidence_refs": [],
            "requested_resources": {}}


def _scope(task_ids=None):
    return {"family": "software", "task_ids": list(task_ids or [TASK_ID])}


def _ctx(profile, digest, **over):
    base = {"candidate_digest": digest, "scope": _scope(),
            "session": "m1-test", "qualify_depth": 0,
            "remaining": {"queries": 16, "model_calls": 2},
            "visible_observation_ids": (), "trusted": False}
    base.update(over)
    return make_ctx(**base)


def test_legacy_sealed_effect_refuses_model_and_revision():
    task = _task()
    model_effect, *_ = policy_assess._effect(task, _model_action())
    assert model_effect["accepted"] is False
    assert "sealed" in model_effect["reason"]
    revision_effect, *_ = policy_assess._effect(task, _revision_action())
    assert revision_effect["accepted"] is False


def test_assessment_model_action_dispatches_and_counts_only_settled_response(
        monkeypatch):
    import experiments.ad01.assessment_profile as shared
    from settlement.common import ResultCode

    calls = []

    def ensure(*args, **kwargs):
        calls.append(("ensure", args, kwargs))
        return SimpleNamespace(code=ResultCode.APPLIED, detail="",
                               data={})

    def dispatch_operation(*args, **kwargs):
        calls.append(("dispatch", args, kwargs))
        return SimpleNamespace(next_decision="terminal")

    monkeypatch.setattr(broker, "ensure_operation", ensure)
    monkeypatch.setattr(broker, "dispatch_operation", dispatch_operation)
    monkeypatch.setattr(
        shared, "_settled_model_response",
        lambda _dsn, _operation_id: ({"text": "settled answer",
                                      "receipt_identity": "gw:answer"}, None))

    effect = dispatch(
        profile_name=ASSESSMENT, record=_record(USE_SOURCE), task=_task(),
        action=_model_action(), ctx=_ctx(ASSESSMENT, _digest(USE_SOURCE)),
        dsn="assessment-store", allocation_id="assessment-allocation",
        gateway=object(), model="assessment-model")

    assert effect["accepted"] is True
    assert effect["model_calls"] == 1
    assert effect["result"]["text"] == "settled answer"
    assert [call[0] for call in calls] == ["ensure", "dispatch"]
    assert calls[0][2]["operation_id"].startswith("m1-assess-")
    assert calls[1][2]["gateway"] is not None


def test_assessment_model_action_without_response_is_not_counted(monkeypatch):
    import experiments.ad01.assessment_profile as shared
    from settlement.common import ResultCode

    calls = []
    monkeypatch.setattr(
        broker, "ensure_operation",
        lambda *args, **kwargs: calls.append("ensure") or SimpleNamespace(
            code=ResultCode.APPLIED, detail="", data={}))
    monkeypatch.setattr(
        broker, "dispatch_operation",
        lambda *args, **kwargs: calls.append("dispatch") or SimpleNamespace(
            next_decision="needs-reconciliation"))
    monkeypatch.setattr(
        shared, "_settled_model_response",
        lambda _dsn, _operation_id: (None, "no settled response"))

    effect = dispatch(
        profile_name=ASSESSMENT, record=_record(USE_SOURCE), task=_task(),
        action=_model_action(), ctx=_ctx(ASSESSMENT, _digest(USE_SOURCE)),
        dsn="assessment-store", allocation_id="assessment-allocation",
        gateway=object(), model="assessment-model")

    assert calls == ["ensure", "dispatch"]
    assert effect["accepted"] is False
    assert effect["model_calls"] == 0
    assert effect["candidate"] is None
    assert "no settled response" in effect["reason"]


def test_settled_model_response_rejects_unsettled_operation(monkeypatch):
    import experiments.ad01.assessment_profile as shared
    from settlement import store

    monkeypatch.setattr(broker, "read_operation", lambda *_args: {
        "settled": False, "dispatch_state": "sent",
        "reconcile_state": "settled"})
    monkeypatch.setattr(store, "operation_receipts", lambda *_args: [{
        "outcome": "success", "settled": True, "usable_result": True,
        "content": {"text": "settled answer"},
        "receipt_identity": "gw:answer"}])

    response, failure = shared._settled_model_response("assessment-store", "op")

    assert response is None
    assert "not settled" in failure


def test_settled_model_response_rejects_successful_unusable_receipt(monkeypatch):
    import experiments.ad01.assessment_profile as shared
    from settlement import store

    monkeypatch.setattr(broker, "read_operation", lambda *_args: {
        "settled": True, "dispatch_state": "sent",
        "reconcile_state": "settled"})
    monkeypatch.setattr(store, "operation_receipts", lambda *_args: [{
        "outcome": "success", "settled": True, "usable_result": False,
        "content": {"text": "settled answer"},
        "receipt_identity": "gw:answer"}])

    response, failure = shared._settled_model_response("assessment-store", "op")

    assert response is None
    assert "successful usable" in failure


def test_shared_assessment_arm_feeds_settled_model_result_to_next_step(
        monkeypatch):
    import experiments.ad01.assessment_profile as shared
    from settlement.common import ResultCode

    source = (
        "def STEP(view, state):\n"
        "    if not state.get('asked'):\n"
        "        return {'action': {'kind': 'request_model',"
        " 'target': view['task_content']['task_id'], 'inputs': {"
        "'prompt': 'inspect', 'max_output_tokens': 64},"
        " 'evidence_refs': [], 'requested_resources': {"
        "'model_calls': 1}}, 'state': {'asked': True}}\n"
        "    if view['last_result'] is None:\n"
        "        return {'action': {'kind': 'stop',"
        " 'target': view['task_content']['task_id'], 'inputs': {},"
        " 'evidence_refs': [], 'requested_resources': {}}, 'state': {}}\n"
        "    return {'action': {'kind': 'use_method',"
        " 'target': view['task_content']['task_id'], 'inputs': {"
        "'method_id': 'seed-sw-greedy', 'max_queries': 4},"
        " 'evidence_refs': [], 'requested_resources': {"
        "'queries': 4}}, 'state': {'done': True}}\n"
    )
    record = _record(source)
    monkeypatch.setattr(
        broker, "ensure_operation",
        lambda *args, **kwargs: SimpleNamespace(code=ResultCode.APPLIED,
                                               detail="", data={}))
    monkeypatch.setattr(
        broker, "dispatch_operation",
        lambda *args, **kwargs: SimpleNamespace(next_decision="terminal"))
    monkeypatch.setattr(
        shared, "_settled_model_response",
        lambda _dsn, _operation_id: ({"text": "settled answer",
                                      "receipt_identity": "gw:answer"}, None))

    arm = shared._shared_assessment_arm(
        record, [TASK_ID], policy_assess.rule_for(resource_ceiling=16),
        "assessment-arm", dsn="assessment-store",
        allocation_id="assessment-allocation", gateway=object(),
        model="assessment-model")

    assert arm["resources"]["model_calls"] == 1
    assert [effect["kind"] for effect in arm["effects"]] == [
        "request_model", "use_method"]
    assert arm["effects"][0]["result"]["text"] == "settled answer"
    assert arm["quality"]["preserved"] == 1


def test_legacy_divergence_demo_same_payload_admitted_by_broker_owner():
    action = _model_action()
    payload = {"model": "policy-request",
               "messages": [{"role": "user",
                             "content": action["inputs"]["prompt"]}],
               "max_output_tokens": 64, "deadline_ms": 300_000,
               "reasoning_effort": "low"}
    assert broker.validate_effect(broker.MODEL_INFERENCE, payload) == payload
    legacy, *_ = policy_assess._effect(_task(), action)
    assert legacy["accepted"] is False


def test_same_program_same_step_action_in_both_profiles():
    record = _record(USE_SOURCE)
    task = _task()
    view = policy_step.materialize_view(
        task=task, observations=[], open_questions=[], last_result=None,
        eligible_methods=["seed-sw-greedy"],
        remaining={"steps": 6, "model_calls": 0, "queries": 4})
    dev = policy_step.run_policy_step(record, view, {})
    assess = policy_step.run_policy_step(record, view, {})
    assert dev["action"] == assess["action"]
    assert dev["action"]["kind"] == "use_method"


def test_unified_method_effect_matches_across_profiles():
    record = _record(USE_SOURCE)
    task = _task()
    action = _use_action()
    dev = dispatch(profile_name=DEVELOPMENT, record=record, task=task,
                   action=action, ctx=_ctx(DEVELOPMENT, _digest(USE_SOURCE)))
    assess = dispatch(profile_name=ASSESSMENT, record=record, task=task,
                      action=action, ctx=_ctx(ASSESSMENT, _digest(USE_SOURCE)))
    assert dev["accepted"] is True
    assert assess["accepted"] is True
    assert dev["owner"] == assess["owner"] == "seeds.run_seed"
    assert dev["selected_identity"] == assess["selected_identity"] \
        == "seed-sw-greedy"
    assert dev["queries"] == assess["queries"]
    assert json.dumps(dev["candidate"], sort_keys=True) == \
        json.dumps(assess["candidate"], sort_keys=True)
    assert dev["destination"] == "production"
    assert assess["destination"] == "assessment-local"


def test_child_action_reaches_real_owner():
    import experiments.ad01.seeds as seedmod
    calls = []
    real = seedmod.run_seed

    def counting(capability, task, *, max_queries=16):
        calls.append(capability["capability_id"])
        return real(capability, task, max_queries=max_queries)

    record = _record(USE_SOURCE)
    task = _task()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(seedmod, "run_seed", counting)
    try:
        dispatch(profile_name=ASSESSMENT, record=record, task=task,
                 action=_use_action(),
                 ctx=_ctx(ASSESSMENT, _digest(USE_SOURCE)))
    finally:
        monkeypatch.undo()
    assert calls == ["seed-sw-greedy"]


def test_no_second_method_interpreter_in_shared_dispatcher():
    import experiments.ad01.assessment_profile as shared
    source = inspect.getsource(shared)
    assert "def _effect" not in source
    assert "def run_member_out_of_process" not in source
    assert "def run_seed" not in source
    assert "seeds.run_seed" in source
    assert "method_exec" in source


def test_model_request_shares_broker_payload_until_declared_difference():
    dev_op = build_model_operation(
        profile_name=DEVELOPMENT, action=_model_action(), model="m",
        session="s", step_index=0)
    assess_op = build_model_operation(
        profile_name=ASSESSMENT, action=_model_action(), model="m",
        session="s", step_index=0)
    assert dev_op["effect"] == assess_op["effect"] == broker.MODEL_INFERENCE
    assert dev_op["payload"] == assess_op["payload"]
    assert dev_op["operation_id"] != assess_op["operation_id"]
    assert assess_op["operation_id"].startswith(
        PROFILES[ASSESSMENT].op_prefix)
    record = _record(USE_SOURCE)
    refused = dispatch(profile_name=ASSESSMENT_RESTRICTED, record=record,
                       task=_task(), action=_model_action(),
                       ctx=_ctx(ASSESSMENT_RESTRICTED, _digest(USE_SOURCE)))
    assert refused["accepted"] is False
    assert ASSESSMENT_RESTRICTED in refused["reason"]


def test_revision_staged_locally_only_trusted_bind():
    source = USE_SOURCE
    record = _record(source)
    task = _task()
    staged = dispatch(profile_name=ASSESSMENT, record=record, task=task,
                      action=_revision_action(),
                      ctx=_ctx(ASSESSMENT, _digest(source)))
    assert staged["accepted"] is True
    assert staged["bound"] is False
    assert staged["destination"] == "assessment-local"
    assert staged["staged"]["parent_digest"] == _digest(source)
    untrusted = bind_revision(profile_name=ASSESSMENT,
                              staged=staged["staged"],
                              candidate_source=source,
                              scope=_scope(), trusted=False)
    assert untrusted["bound"] is False
    tampered = bind_revision(profile_name=DEVELOPMENT,
                             staged=staged["staged"],
                             candidate_source=source + "\n",
                             scope=_scope(), trusted=True)
    assert tampered["bound"] is False
    wrong_scope = bind_revision(profile_name=DEVELOPMENT,
                                staged=staged["staged"],
                                candidate_source=source,
                                scope=_scope(["other-task"]), trusted=True)
    assert wrong_scope["bound"] is False
    bound = bind_revision(profile_name=DEVELOPMENT,
                          staged=staged["staged"],
                          candidate_source=source,
                          scope=_scope(), trusted=True)
    assert bound["bound"] is True
    assert bound["candidate_digest"] == _digest(source)


def test_production_revision_assessment_uses_shared_dispatcher(monkeypatch):
    source = USE_SOURCE
    candidate_digest = _digest(source)
    incumbent = policy_step.make_policy_artifact(source, origin="authored-control")
    panel = policy_assess.panel_for(scope={"family": "software"}, world=0,
                                    seed="proposal-1")
    rule = policy_assess.rule_for(resource_ceiling=16)
    frozen = {"panel_digest": policy_assess._panel_digest(panel),
              "rule_id": rule["rule_id"],
              "rule_digest": policy_assess._rule_digest(
                  policy_assess._rule_identity(rule))}
    persisted = {}

    def read_journal(_dsn, request_id):
        if request_id == policy_assess._protocol_request_id("proposal-1"):
            return frozen
        return None

    def persist_assessment(_dsn, record):
        persisted.update(record)
        return record

    monkeypatch.setattr(policy_assess, "_read_journal", read_journal)
    monkeypatch.setattr(policy_assess, "_persist_assessment", persist_assessment)
    monkeypatch.setattr(
        policy_assess, "assess_policy",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("production assessment used legacy dispatcher")))
    monkeypatch.setattr(
        policy_assess, "freeze_protocol", lambda *args, **kwargs: frozen)
    monkeypatch.setattr(
        records, "open_revision_proposal",
        lambda *args, **kwargs: {"proposal_id": "proposal-1",
                                "parent_digest": candidate_digest})
    monkeypatch.setattr(
        records, "freeze_candidate",
        lambda *args, **kwargs: {"source": source,
                                "candidate_digest": candidate_digest})
    monkeypatch.setattr(
        records, "load_assessment",
        lambda *args, **kwargs: dict(persisted))
    monkeypatch.setattr(
        construct, "construct_policy",
        lambda *args, **kwargs: {"policy_source": source,
                                  "capability_id": "candidate-1",
                                  "lineage": {"calls_made": 0}})
    investigation = {
        "basis_references": ["obs-real"],
        "next_action": {"kind": "policy_revision", "task_id": TASK_ID},
        "revision_proposal": {"parent_digest": candidate_digest,
                              "scope": {"family": "software"}},
    }
    seen = {"observations": [{"observation_id": "obs-real",
                              "task_id": TASK_ID,
                              "verdict": "not_preserved"}],
            "remaining": {"model_calls": 2}}
    construction = {"dsn": "unused", "cid": "ad01-w0-I-00",
                    "gateway": object(), "model": "model",
                    "budget": {"max_output_tokens": 64},
                    "study_root": "study", "world": 0,
                    "incumbent_policy": incumbent}
    observation, episode, spend = trajectory._construct_policy_revision(
        investigation, seen,
        {"observation_id": "seed", "task_id": TASK_ID}, construction,
        {"construction_calls": 0, "model_calls": 0})
    assert spend == 16
    assert episode["assessment_status"] == "complete"
    candidate_effect = episode["assessment"]["arms"]["candidate"]["effects"][0]
    assert candidate_effect["owner"] == "seeds.run_seed"
    assert observation["detail"]["kind"] == "policy_revision"


def test_nested_qualification_bounded_and_audit_never_promotes():
    source = USE_SOURCE
    record = _record(source)
    nested = {"kind": "propose_revision", "target": TASK_ID,
              "inputs": {"request": "assessment", "motivation": "recurse"},
              "evidence_refs": [], "requested_resources": {}}
    deep = dispatch(profile_name=ASSESSMENT, record=record, task=_task(),
                    action=nested,
                    ctx=_ctx(ASSESSMENT, _digest(source), qualify_depth=1))
    assert deep["accepted"] is False
    assert "depth" in deep["reason"]
    audit = dispatch(profile_name=AUDIT, record=record, task=_task(),
                     action=nested,
                     ctx=_ctx(AUDIT, _digest(source)))
    assert audit["accepted"] is False
    staged = dispatch(profile_name=ASSESSMENT, record=record, task=_task(),
                      action=_revision_action(),
                      ctx=_ctx(ASSESSMENT, _digest(source)))
    audit_bind = bind_revision(profile_name=AUDIT, staged=staged["staged"],
                               candidate_source=source, scope=_scope(),
                               trusted=True)
    assert audit_bind["bound"] is False


def test_audit_cannot_write_production():
    record = _record(USE_SOURCE)
    action = _use_action()
    action["inputs"] = dict(action["inputs"], destination="production")
    refused = dispatch(profile_name=AUDIT, record=record, task=_task(),
                       action=action,
                       ctx=_ctx(AUDIT, _digest(USE_SOURCE)))
    assert refused["accepted"] is False
    assert "production" in refused["reason"]


def test_source_freeze_checked_before_any_owner_call():
    import experiments.ad01.seeds as seedmod
    calls = []
    real = seedmod.run_seed

    def counting(capability, task, *, max_queries=16):
        calls.append(1)
        return real(capability, task, max_queries=max_queries)

    record = _record(USE_SOURCE)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(seedmod, "run_seed", counting)
    try:
        refused = dispatch(profile_name=ASSESSMENT, record=record,
                           task=_task(), action=_use_action(),
                           ctx=_ctx(ASSESSMENT, "0" * 64))
    finally:
        monkeypatch.undo()
    assert refused["accepted"] is False
    assert "identity" in refused["reason"]
    assert calls == []
    scoped_out = dispatch(profile_name=ASSESSMENT, record=record,
                          task=_task(), action=_use_action(),
                          ctx=_ctx(ASSESSMENT, _digest(USE_SOURCE),
                                   scope=_scope(["other-task"])))
    assert scoped_out["accepted"] is False
    assert "scope" in scoped_out["reason"]


def test_unnamed_use_is_refused_and_construct_still_defaults():
    record = _record(USE_SOURCE)
    task = _task()
    # An unnamed use_method is refused: it names a method it did not build
    # (a60798d). The family default survives only for construct_method, the
    # action that produces one, and it still reports its identity.
    unnamed = _use_action()
    unnamed["inputs"] = {"max_queries": 4}
    refused = dispatch(profile_name=ASSESSMENT, record=record, task=task,
                       action=unnamed,
                       ctx=_ctx(ASSESSMENT, _digest(USE_SOURCE)))
    assert refused["accepted"] is False
    assert "names no task method" in refused["reason"]
    assert refused["selected_identity"] is None
    assert refused["candidate"] is None

    built = {"kind": "construct_method", "target": TASK_ID,
             "inputs": {"max_queries": 4}, "evidence_refs": [],
             "requested_resources": {"queries": 4}}
    effect = dispatch(profile_name=ASSESSMENT, record=record, task=task,
                      action=built,
                      ctx=_ctx(ASSESSMENT, _digest(USE_SOURCE)))
    assert effect["accepted"] is True
    assert effect["selected_identity"] == "seed-sw-greedy"
    assert effect["owner"] == "seeds.run_seed"
    assert effect["candidate"] is not None

    unknown = _use_action(method_id="missing")
    unknown_refused = dispatch(profile_name=ASSESSMENT, record=record,
                               task=task, action=unknown,
                               ctx=_ctx(ASSESSMENT, _digest(USE_SOURCE)))
    assert unknown_refused["accepted"] is False
    assert "unknown task method" in unknown_refused["reason"]


def test_sealed_observations_stay_out_of_assessment_views():
    task = dict(_task())
    task["hidden_answer"] = "literal-secret-witness-answer"
    observations = [{"observation_id": "sealed-1", "task_id": TASK_ID,
                     "verdict": "preserved", "access_label": "hidden",
                     "hidden_answer": "literal-secret-witness-answer",
                     "detail": {}}]
    view = policy_step.materialize_view(
        task=task, observations=observations, open_questions=[],
        last_result=None, eligible_methods=["seed-sw-greedy"],
        remaining={"steps": 6, "model_calls": 0, "queries": 4})
    assert "literal-secret-witness-answer" not in json.dumps(view,
                                                             sort_keys=True)
    record = _record(USE_SOURCE)
    action = _use_action(refs=["sealed-1"])
    refused = dispatch(profile_name=ASSESSMENT, record=record, task=_task(),
                       action=action,
                       ctx=_ctx(ASSESSMENT, _digest(USE_SOURCE),
                                visible_observation_ids=()))
    assert refused["accepted"] is False
    assert "visible" in refused["reason"]


def test_profile_registry_declares_differences():
    assert set(PROFILES) == {DEVELOPMENT, ASSESSMENT,
                             ASSESSMENT_RESTRICTED, AUDIT}
    assert PROFILES[DEVELOPMENT].destination == "production"
    assert PROFILES[ASSESSMENT].destination == "assessment-local"
    assert PROFILES[ASSESSMENT].allow_model is True
    assert PROFILES[ASSESSMENT_RESTRICTED].allow_model is False
    assert PROFILES[AUDIT].allow_revision_bind is False
    assert PROFILES[AUDIT].allow_nested_qualify is False


def test_method_owners_receive_stripped_task_only():
    import experiments.ad01.seeds as seedmod
    seen = []
    real = seedmod.run_seed

    def capturing(capability, task, *, max_queries=16):
        seen.append(dict(task))
        return real(capability, task, max_queries=max_queries)

    task = dict(_task())
    task["hidden_answer"] = "literal-secret-task-answer"
    task["access_label"] = "hidden"
    record = _record(USE_SOURCE)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(seedmod, "run_seed", capturing)
    try:
        effect = dispatch(profile_name=ASSESSMENT, record=record, task=task,
                          action=_use_action(),
                          ctx=_ctx(ASSESSMENT, _digest(USE_SOURCE)))
    finally:
        monkeypatch.undo()
    assert effect["accepted"] is True
    assert len(seen) == 1
    assert "literal-secret-task-answer" not in json.dumps(seen[0],
                                                          sort_keys=True)
    assert "hidden_answer" not in seen[0]
    assert "access_label" not in seen[0]
    assert seen[0]["task_id"] == TASK_ID
