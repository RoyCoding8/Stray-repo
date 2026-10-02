from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments.ad01 import frontier
from experiments.ad01 import improve_channel as channel
from experiments.ad01 import live_construct as live
from experiments.ad01 import method_exec
from experiments.ad01 import policy_step
from experiments.ad01 import worlds
from settlement.common import ResultCode


def _store(tmp_path):
    return live.ensure_live_store(
        tmp_path / "store.json",
        live.live_mission(
            live.LIVE_MISSION_OBJECTIVE,
            [{"instrument": "boolean-rule-v1", "split": "dev", "seed": 4}]),
        dict(live.LIVE_AUTHORITY))


def _opportunity(store, opportunity_id):
    store.propose({
        "opportunity_id": opportunity_id,
        "mission_link": live.LIVE_MISSION_OBJECTIVE,
        "question": "observe",
        "intervention": {"instrument": "boolean-rule-v1",
                         "target": "rule-dev-0004", "inputs": {}},
        "resources": {"queries": 1, "steps": 1}})


def _forged_acquired_package(store):
    from settlement.gateway import ModelRequest, ModelResponse, Usage

    class Gateway:
        def infer(self, request):
            return ModelResponse(
                request.operation_id,
                json.dumps({"entry": store.active_package["imp_source"]}),
                {}, Usage(), "stop")

    guard = live.LiveGuard(Gateway(), pinned_model="test-model", ceiling=1)
    request = ModelRequest(
        model="test-model",
        messages=({"role": "user", "content": "construct"},),
        max_output_tokens=8,
        deadline_ms=1000,
        operation_id="op-forged-adoption")
    guard.infer(request, evidence={
        "arm": "test", "task": "rule-dev-0004", "attempt": 1,
        "raw_prompt": "construct"})
    dispatch = guard.provenance(request.operation_id)
    package = live.parse_and_build_live_package(
        store.active_package,
        json.dumps({"entry": store.active_package["imp_source"]}),
        "forged-adoption-r1",
        dispatch=dispatch)
    return package, guard, request.operation_id


def test_store_adoption_refuses_forged_acquired_package_without_evidence(tmp_path):
    store = _store(tmp_path)
    store.bind_active(channel.make_control("low"))
    package, _, _ = _forged_acquired_package(store)

    with pytest.raises(frontier.Refused, match="acquisition evidence"):
        store.adopt_revision(package)

    assert store.treatment_arms["acquired"] == []


def test_store_adoption_accepts_durable_acquisition_evidence(tmp_path):
    store = _store(tmp_path)
    base = channel.make_control("low")
    store.bind_active(base)
    package, guard, operation_id = _forged_acquired_package(store)
    dispatch = guard.provenance(operation_id)
    store.record_evidence(dispatch)
    finalization = guard.finalize_evidence(
        operation_id,
        parse_outcome="accepted",
        accepted_candidate_digest=package["package_digest"],
        parsed_source_digest=package["imp_digest"],
        package_digest=package["package_digest"],
        parent_digest=package["parent_digest"],
        round_no=1)
    store.record_evidence(finalization)

    bound = store.adopt_revision(
        package, acquisition_evidence=finalization)

    assert bound["package_digest"] == package["package_digest"]
    assert bound["op_source"] == base["op_source"]
    assert bound["op_digest"] == base["op_digest"]
    assert store.treatment_arms["acquired"] == [package]


def test_finalization_replay_is_idempotent_and_conflicts_refuse(tmp_path):
    store = _store(tmp_path)
    store.bind_active(channel.make_control("low"))
    package, guard, operation_id = _forged_acquired_package(store)
    arguments = {
        "parse_outcome": "accepted",
        "accepted_candidate_digest": package["package_digest"],
        "parsed_source_digest": package["imp_digest"],
        "package_digest": package["package_digest"],
        "parent_digest": package["parent_digest"],
        "round_no": 1,
    }
    first = guard.finalize_evidence(operation_id, **arguments)

    assert guard.finalize_evidence(operation_id, **arguments) == first
    with pytest.raises(live.LiveRefused, match="finalization"):
        guard.finalize_evidence(
            operation_id, **{**arguments, "parse_outcome": "parse-failed"})


def test_store_adoption_refuses_operational_source_mutation(tmp_path):
    store = _store(tmp_path)
    base = channel.make_control("low")
    store.bind_active(base)
    package, guard, operation_id = _forged_acquired_package(store)
    mutated = dict(package)
    mutated["op_source"] += "\n# changed"
    mutated["op_digest"] = frontier.source_digest(mutated["op_source"])
    mutated["package_digest"] = frontier.package_digest(mutated)
    dispatch = guard.provenance(operation_id)
    store.record_evidence(dispatch)
    finalization = guard.finalize_evidence(
        operation_id,
        parse_outcome="accepted",
        accepted_candidate_digest=mutated["package_digest"],
        parsed_source_digest=mutated["imp_digest"],
        package_digest=mutated["package_digest"],
        parent_digest=mutated["parent_digest"],
        round_no=1)
    store.record_evidence(finalization)

    with pytest.raises(frontier.Refused, match="operational source"):
        store.adopt_revision(mutated, acquisition_evidence=finalization)

    assert store.active_digest == base["package_digest"]
    assert store.treatment_arms["acquired"] == []


def test_store_settlement_refuses_foreign_operation_for_effect(tmp_path):
    store = _store(tmp_path)
    base = channel.make_control("low")
    store.bind_active(base)
    _opportunity(store, "opp-foreign")
    effect = store.accept(
        "opp-foreign", base["package_digest"],
        effect_identity={"operation_id": "op-real"})

    with pytest.raises(frontier.Refused, match="operation identity"):
        store.observe({
            "observation_id": "obs-foreign",
            "effect_id": effect["effect_id"],
            "operation_id": "op-foreign",
            "task": "opp-foreign",
            "verdict": "observed"})

    with pytest.raises(frontier.Refused, match="operation identity"):
        store.observe({
            "observation_id": "obs-foreign-without-effect",
            "operation_id": "op-foreign",
            "task": "opp-foreign",
            "verdict": "observed"})

    with pytest.raises(frontier.Refused, match="needs attribution"):
        store.observe({
            "observation_id": "obs-foreign-without-identity",
            "task": "opp-foreign",
            "verdict": "observed"})

    assert store.pending_effects[0]["effect_id"] == effect["effect_id"]


class _FakeCursor:
    def __init__(self):
        self.row = None

    def execute(self, sql, params=()):
        self.row = ("generation",) if "allocations" in sql else None

    def fetchone(self):
        return self.row


class _FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=()):
        cursor = _FakeCursor()
        cursor.execute(sql, params)
        return cursor


class _DurableCursor:
    def __init__(self, state):
        self.state = state

    def execute(self, sql, params=()):
        self.sql = sql
        self.params = params

    def fetchone(self):
        if "FROM operations" in self.sql:
            # Six columns, matching method_exec._durable_receipt's unpack:
            # dispatch_state, reconcile_state, settled, allocation_id,
            # payload_digest, payload. A narrower row here raises ValueError
            # on unpack before the state under test is ever read, which is how
            # this fake went stale without anybody noticing.
            return (self.state, "none", False, "alloc-test", "digest-test", {})
        return None

    def fetchall(self):
        return []


class _DurableConnection:
    def __init__(self, state):
        self.state = state

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=()):
        cursor = _DurableCursor(self.state)
        cursor.execute(sql, params)
        return cursor


def _durable_substitution(monkeypatch, source_file, replacement):
    from settlement import db

    monkeypatch.setattr(db, "connect", lambda dsn: _FakeConnection())
    dispatched = []

    def ensure_operation(dsn, **kwargs):
        payload = kwargs["payload"]
        work = Path(payload["argv"][2])
        (work / source_file).write_text(replacement, encoding="utf-8")
        return SimpleNamespace(code=ResultCode.APPLIED, detail="")

    def dispatch(*args, **kwargs):
        dispatched.append(True)
        return None

    monkeypatch.setattr(method_exec.broker, "ensure_operation", ensure_operation)
    monkeypatch.setattr(method_exec.broker, "dispatch_operation", dispatch)
    return dispatched


def test_durable_child_receipt_refuses_conflicted_or_unresolved_operation(
        monkeypatch):
    from settlement import db

    for state in ("conflict", "unresolved"):
        monkeypatch.setattr(
            db, "connect", lambda dsn, state=state: _DurableConnection(state))
        with pytest.raises(method_exec.MethodExecutionError,
                           match="conflicted or unresolved"):
            method_exec._durable_receipt("fake-dsn", "op-child")


def test_durable_step_rechecks_source_after_receipt(monkeypatch):
    from settlement import db

    monkeypatch.setattr(db, "connect", lambda dsn: _FakeConnection())
    work = {}
    dispatched = []

    def ensure_operation(dsn, **kwargs):
        work["path"] = Path(kwargs["payload"]["argv"][2])
        (work["path"] / "policy.py").write_text(
            "def STEP(view, state):\n"
            "    return {\"action\": {\"kind\": \"stop\"}, \"state\": {}}\n",
            encoding="utf-8")
        return SimpleNamespace(code=ResultCode.APPLIED, detail="")

    def dispatch(*args, **kwargs):
        dispatched.append(True)
        return None

    monkeypatch.setattr(method_exec.broker, "ensure_operation", ensure_operation)
    monkeypatch.setattr(method_exec.broker, "dispatch_operation", dispatch)
    source = ("def STEP(view, state):\n"
              "    action = {\"kind\": \"stop\", \"target\": \"t\","
              " \"inputs\": {}, \"evidence_refs\": [],"
              " \"requested_resources\": {}}\n"
              "    return {\"action\": action, \"state\": {}}\n")
    view = policy_step.materialize_view(
        task=worlds.load_task(worlds.FROZEN_DIR, "ad01-w0-dev-sw-00"),
        observations=[], open_questions=[], last_result=None,
        eligible_methods=[], remaining={"steps": 1})

    with pytest.raises(method_exec.MethodExecutionError,
                       match="staged source digest mismatch"):
        method_exec.run_step_out_of_process(
            source, view, {}, dsn="fake-dsn", allocation_id="alloc-recheck",
            operation_id="op-step-recheck")

    assert dispatched == []


def test_durable_member_rejects_substitution_before_broker_dispatch(monkeypatch):
    source = ("def carried(task, oracle):\n"
              "    return {\"candidate\": {}, \"queries\": 0}\n")
    replacement = source.replace("carried", "substituted")
    dispatched = _durable_substitution(
        monkeypatch, "member.py", replacement)
    member = {"capability_id": "durable-source-test",
              "method_source": source, "entry": "carried"}

    with pytest.raises(method_exec.MethodExecutionError,
                       match="staged source digest mismatch"):
        method_exec.run_member_out_of_process(
            member, {}, dsn="fake-dsn", allocation_id="alloc-member",
            operation_id="op-member-substitution")

    assert dispatched == []


def _usage_gateway(usage):
    from settlement.gateway import ModelResponse

    class Gateway:
        def __init__(self):
            self.calls = 0

        def infer(self, request):
            self.calls += 1
            return ModelResponse(request.operation_id, "ok", {}, usage, "stop")

    return Gateway()


def test_live_guard_allows_explicit_billed_zero():
    from settlement.gateway import ModelRequest, Usage

    measured_zero = _usage_gateway(Usage(
        charge_units=0, charge_scale=1_000, billed=False))
    guard = live.LiveGuard(measured_zero, pinned_model="test-model", ceiling=2)
    for operation_id in ("op-zero-1", "op-zero-2"):
        guard.infer(ModelRequest(
            model="test-model", messages=(), max_output_tokens=8,
            deadline_ms=1000, operation_id=operation_id))
    assert measured_zero.calls == 2
    assert guard.cost_blocked is None


def test_live_guard_keeps_unbilled_zero_unknown_and_blocks_later_dispatch():
    from settlement.gateway import ModelRequest, Usage

    unknown_zero = _usage_gateway(Usage(charge_units=0, billed=None))
    guard = live.LiveGuard(unknown_zero, pinned_model="test-model", ceiling=2)
    guard.infer(ModelRequest(
        model="test-model", messages=(), max_output_tokens=8,
        deadline_ms=1000, operation_id="op-unknown-zero"))
    assert unknown_zero.calls == 1
    assert guard.is_cost_blocked() is True
    with pytest.raises(live.LiveRefused):
        guard.infer(ModelRequest(
            model="test-model", messages=(), max_output_tokens=8,
            deadline_ms=1000, operation_id="op-unknown-zero-2"))
    assert unknown_zero.calls == 1


def test_conflicting_evidence_identity_preserves_first_record(tmp_path):
    store = _store(tmp_path)
    first = frontier.make_evidence_record(
        "m4-observation", "op-conflict", "success",
        receipt_identity="receipt-conflict", task_id="rule-dev-0004",
        result_digest="a" * 64, details={"raw_payload": {"value": "first"}})
    store.record_evidence(first)
    conflicting = frontier.make_evidence_record(
        "m4-observation", "op-conflict", "success",
        receipt_identity="receipt-conflict", task_id="rule-dev-0004",
        result_digest="b" * 64, details={"raw_payload": {"value": "second"}})

    with pytest.raises(frontier.Refused, match="evidence identity|conflict"):
        store.record_evidence(conflicting)

    assert store.evidence == [first]


def test_duplicate_action_identity_preserves_first_outcome(tmp_path):
    store = _store(tmp_path)
    key = {"instrument": "boolean-rule-v1", "inputs": {"x": 3},
           "environment": store.environment_digest}
    store.record_outcome(key, {"value": "first"})

    with pytest.raises(frontier.Refused, match="action|outcome|duplicate"):
        store.record_outcome(key, {"value": "second"})

    assert store.replay(key)["outcome"] == {"value": "first"}


def test_conflicting_observation_identity_preserves_first_record(tmp_path):
    store = _store(tmp_path)
    first = {"observation_id": "obs-conflict", "task": "rule-dev-0004",
             "verdict": "first"}
    store.observe(first)
    conflicting = dict(first, verdict="second")

    with pytest.raises(frontier.Refused, match="observation|identity|conflict"):
        store.observe(conflicting)

    assert store.observations == [first]
