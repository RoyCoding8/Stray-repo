"""Live lane integration: doubles only, no gateway, no database."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.ad01 import boolean_rule as rules
from experiments.ad01 import frontier
from experiments.ad01 import improve_channel as channel
from experiments.ad01 import live_construct as live
from experiments.ad01 import trajectory
from scripts import invl02_live as driver


class _ScriptGateway:
    def __init__(self, texts=None, error=None, usage=None):
        self.texts = list(texts or [])
        self.error = error
        self.usage = usage
        self.requests = []

    def check_discovery(self):
        return "configured"

    def check_auth(self):
        return "authenticated"

    def cancel(self, operation_id):
        return True

    def infer(self, request):
        from settlement.gateway import GatewayError, GatewayErrorKind, \
            ModelResponse, Usage
        self.requests.append(request)
        if self.error is not None:
            return self.error
        if not self.texts:
            return ModelResponse(request.operation_id, "", {}, Usage(),
                                 "stop")
        return ModelResponse(request.operation_id, self.texts.pop(0), {},
                             self.usage or Usage(), "stop")


def _guard(texts=None, ceiling=12, error=None):
    return live.LiveGuard(_ScriptGateway(texts, error),
                         pinned_model="test-model", ceiling=ceiling)


def test_guard_pins_model():
    from settlement.gateway import ModelRequest
    guard = _guard(["hi"])
    with pytest.raises(live.LiveRefused):
        guard.infer(ModelRequest(model="other", messages=(), 
                                 max_output_tokens=8, deadline_ms=1000,
                                 operation_id="op-1"))


def test_guard_refuses_over_ceiling_before_dispatch():
    from settlement.gateway import ModelRequest
    delegate = _ScriptGateway(["hi"])
    guard = live.LiveGuard(delegate, pinned_model="test-model",
                           ceiling=1, already_spent=1)
    with pytest.raises(live.LiveRefused):
        guard.infer(ModelRequest(model="test-model", messages=(),
                                 max_output_tokens=8, deadline_ms=1000,
                                 operation_id="op-1"))
    assert delegate.requests == []


def test_guard_retries_empty_then_records_ledger():
    from settlement.gateway import ModelRequest
    guard = _guard(["", "", "{}", ])
    response = guard.infer(ModelRequest(
        model="test-model", messages=(), max_output_tokens=8,
        deadline_ms=1000, operation_id="op-1"))
    assert response.text == "{}"
    assert [e["outcome"] for e in guard.ledger] == ["unknown", "unknown",
                                                   "success"]
    assert guard.dispatch_count == 3


def test_guard_preserves_unknown_usage_in_ledger_and_dispatch():
    from settlement.gateway import ModelRequest, Usage

    usage = Usage(input_tokens=None, output_tokens=None, charge_units=None,
                  charge_scale=None, billed=None)
    guard = live.LiveGuard(
        _ScriptGateway(["ok"], usage=usage), pinned_model="test-model",
        ceiling=1)
    response = guard.infer(ModelRequest(
        model="test-model", messages=({"role": "user", "content": "raw"},),
        max_output_tokens=8, deadline_ms=1000, operation_id="op-unknown"))
    expected = {
        "input_tokens": "unknown", "output_tokens": "unknown",
        "charge_units": "unknown", "charge_scale": "unknown",
        "provider_enforced_ceiling": False, "billed": "unknown"}

    assert response.text == "ok"
    assert guard.ledger[0]["usage"] == expected
    dispatch = guard.provenance("op-unknown")
    assert dispatch["usage"] == expected
    assert dispatch["details"]["usage"] == expected
    assert dispatch["charge_units"] == "unknown"
    assert dispatch["billed"] == "unknown"


def test_guard_preserves_route_error_metadata():
    from settlement.gateway import GatewayError, GatewayErrorKind, \
        GatewayRouteError, ModelRequest
    error = GatewayError(
        GatewayErrorKind.TRANSPORT, "route mismatch", False, "op-route",
        response_received=True, response_status=502,
        response_digest="response-sha", route_error=GatewayRouteError.RESPONSE_METADATA)
    guard = _guard(error=error)
    response = guard.infer(ModelRequest(
        model="test-model", messages=({"role": "user", "content": "raw"},),
        max_output_tokens=8, deadline_ms=1000, operation_id="op-route"))
    assert response is error
    entry = guard.provenance("op-route")
    assert entry["parse_outcome"] == "route-refused"
    assert entry["diagnosis"]["stage"] == "route"
    assert entry["route_error"] == "response_metadata"
    assert entry["response_received"] is True
    assert entry["response_status"] == 502
    assert entry["response_digest"] == "response-sha"


def test_guard_blocks_unknown_billing_even_with_zero_charge():
    from settlement.gateway import ModelRequest, Usage
    usage = Usage(charge_units=0, billed=None)
    delegate = _ScriptGateway(["ok", "later"], usage=usage)
    guard = live.LiveGuard(delegate, pinned_model="test-model", ceiling=2)
    request = ModelRequest(
        model="test-model", messages=({"role": "user", "content": "raw"},),
        max_output_tokens=8, deadline_ms=1000, operation_id="op-zero-unknown")
    guard.infer(request)
    with pytest.raises(live.LiveRefused, match="unknown possible cost"):
        guard.infer(ModelRequest(
            model="test-model", messages=({"role": "user", "content": "raw"},),
            max_output_tokens=8, deadline_ms=1000, operation_id="op-zero-later"))
    assert len(delegate.requests) == 1


def test_guard_preserves_measured_usage_in_ledger_and_dispatch():
    from settlement.gateway import ModelRequest, Usage

    usage = Usage(input_tokens=3, output_tokens=4, charge_units=5,
                  charge_scale=100, provider_enforced_ceiling=True,
                  billed=True)
    guard = live.LiveGuard(
        _ScriptGateway(["ok"], usage=usage), pinned_model="test-model",
        ceiling=1)
    guard.infer(ModelRequest(
        model="test-model", messages=({"role": "user", "content": "raw"},),
        max_output_tokens=8, deadline_ms=1000, operation_id="op-measured"))
    expected = {
        "input_tokens": 3, "output_tokens": 4, "charge_units": 5,
        "charge_scale": 100, "provider_enforced_ceiling": True,
        "billed": True}

    assert guard.ledger[0]["usage"] == expected
    assert guard.provenance("op-measured")["usage"] == expected


def test_guard_blocks_on_nonzero_cost():
    from settlement.gateway import GatewayError, GatewayErrorKind, \
        ModelRequest, Usage
    error = GatewayError(GatewayErrorKind.TRANSPORT, "boom", False,
                         "op-1", Usage(charge_units=5))
    guard = _guard(error=error)
    guard.infer(ModelRequest(model="test-model", messages=(),
                             max_output_tokens=8, deadline_ms=1000,
                             operation_id="op-1"))
    assert guard.cost_blocked is not None
    with pytest.raises(live.LiveRefused):
        guard.infer(ModelRequest(model="test-model", messages=(),
                                 max_output_tokens=8, deadline_ms=1000,
                                 operation_id="op-2"))


def test_retryable_error_retries_within_bound():
    from settlement.gateway import GatewayError, GatewayErrorKind, \
        ModelRequest
    delegate = _ScriptGateway()
    errors = [GatewayError(GatewayErrorKind.TIMEOUT, "slow", True,
                           "op-1")]
    delegate.error = errors[0]
    guard = live.LiveGuard(delegate, pinned_model="test-model",
                           ceiling=12)
    guard.infer(ModelRequest(model="test-model", messages=(),
                             max_output_tokens=8, deadline_ms=1000,
                             operation_id="op-1"))
    assert len(delegate.requests) == 4


def test_guard_records_unexpected_adapter_exception_before_reraising():
    from settlement.gateway import ModelRequest

    class RaisingGateway(_ScriptGateway):
        def infer(self, request):
            raise RuntimeError("adapter exploded")

    guard = live.LiveGuard(RaisingGateway(), pinned_model="test-model",
                           ceiling=1)
    with pytest.raises(RuntimeError, match="adapter exploded"):
        guard.infer(ModelRequest(
            model="test-model", messages=({"role": "user", "content": "raw"},),
            max_output_tokens=8, deadline_ms=1000,
            operation_id="op-raises"))
    assert guard.dispatch_count == 1
    assert len(guard.ledger) == 1
    entry = guard.ledger[0]
    assert entry["operation_id"] == "op-raises"
    assert entry["outcome"] == "unresolved"
    assert entry["exception_class"] == "RuntimeError"
    assert entry["prompt_digest"] == live.source_digest("raw")
    assert entry["usage"] == {
        "input_tokens": "unknown", "output_tokens": "unknown",
        "charge_units": "unknown", "charge_scale": "unknown",
        "provider_enforced_ceiling": "unknown", "billed": "unknown"}


def test_digest_chain_links_response_to_effect():
    chain = live.digest_chain(
        "raw", "def STEP(view, state): return {}",
        {"operation_id": "op-1", "outcome": "success"},
        {"kind": "diagnose"}, {"verdict": "observed"})
    assert chain["response_digest"] == live.response_digest("raw")
    assert chain["source_digest"] != chain["response_digest"]
    assert chain["child"]["outcome"] == "success"


def _probe_store(tmp_path):
    store = frontier.create_store(
        tmp_path / "store.json", namespace=frontier.NAMESPACE,
        mission={"objective": "probe", "environments": [{"split": "dev",
                                                         "seed": 4}]},
        authority={"queries": 16, "steps": 12})
    store.propose({
        "opportunity_id": "opp-probe",
        "mission_link": "probe",
        "question": "observe input 3",
        "intervention": {
            "instrument": "boolean-rule-v1",
            "target": "rule-dev-0004",
            "inputs": {"x": 3}},
        "resources": {"queries": 1, "steps": 1}})
    store.bind_active(channel.make_control("low"))
    return store


def test_probe_observes_and_settles_the_pending_effect(
        tmp_path, monkeypatch):
    store = _probe_store(tmp_path)
    original_query = channel._boolean_rule.RuleSession.query

    def attributed_query(session, x):
        pending = store.pending_effects
        assert len(pending) == 1
        assert pending[0]["opportunity_id"] == "opp-probe"
        return original_query(session, x)

    monkeypatch.setattr(
        channel._boolean_rule.RuleSession, "query", attributed_query)
    result = channel.execute_operate_action(
        store,
        {"kind": "probe",
         "inputs": {"opportunity_id": "opp-probe", "x": 3},
         "requested_resources": {"queries": 1, "steps": 1}},
        rules.make_task("dev", 4))

    assert result["status"] == "observed"
    assert store.pending_effects == []
    assert len(store.settled_effects) == 1
    settled = store.settled_effects[0]
    observation = store.observations[0]
    assert settled["observation_id"] == observation["observation_id"]
    assert observation["effect_id"] == settled["effect_id"]
    assert observation["operation_id"] == settled["expected_identity"][
        "operation_id"]


def test_probe_refuses_before_query_without_an_admitted_effect(
        tmp_path, monkeypatch):
    store = _probe_store(tmp_path)
    store._doc["opportunities"].clear()
    store.save()

    def unexpected_query(session, x):
        raise AssertionError("probe query ran without an admitted effect")

    monkeypatch.setattr(
        channel._boolean_rule.RuleSession, "query", unexpected_query)
    result = channel.execute_operate_action(
        store,
        {"kind": "probe",
         "inputs": {"opportunity_id": "opp-missing", "x": 3},
         "requested_resources": {"queries": 1, "steps": 1}},
        rules.make_task("dev", 4))

    assert result == {
        "status": "refused",
        "reason": "opportunity 'opp-missing' is not admissible"}
    assert store.observations == []
    assert store.pending_effects == []
    assert store.settled_effects == []




def test_probe_refusal_does_not_admit_or_spend_when_budget_is_exhausted(
        tmp_path):
    store = _probe_store(tmp_path)
    before = store.authority

    result = channel.execute_operate_action(
        store,
        {"kind": "probe",
         "inputs": {"opportunity_id": "opp-probe", "x": 3},
         "requested_resources": {"queries": 10_000, "steps": 0}},
        rules.make_task("dev", 4))

    assert result["status"] == "refused"
    assert store.authority == before
    assert store.pending_effects == []
    assert store.settled_effects == []
    assert store.observations == []
    assert store._doc["opportunities"]["opp-probe"]["status"] == "admissible"


def test_investigate_refusal_without_bound_program_preserves_authority(
        tmp_path):
    store = _probe_store(tmp_path)
    store._doc["active_package"] = None
    store.save()
    before = dict(store.authority)
    with pytest.raises(frontier.Refused, match="bound program"):
        channel.execute_operate_action(
            store,
            {"kind": "investigate",
             "inputs": {"opportunity_id": "opp-probe"},
             "requested_resources": {"queries": 1, "steps": 1}})
    assert store.authority == before


def test_admitted_probe_recovery_reuses_effect_without_duplicate_effect(
        tmp_path, monkeypatch):
    store = _probe_store(tmp_path)
    package = store.active_package
    effect = store.accept("opp-probe", package["package_digest"])
    calls = []
    original_query = channel._boolean_rule.RuleSession.query

    def counted_query(session, x):
        calls.append(x)
        return original_query(session, x)

    monkeypatch.setattr(
        channel._boolean_rule.RuleSession, "query", counted_query)
    action = {"kind": "probe",
              "inputs": {"opportunity_id": "opp-probe", "x": 3},
              "requested_resources": {"queries": 1, "steps": 1}}
    before = dict(store.authority)
    first = channel.execute_operate_action(store, action, rules.make_task("dev", 4))
    second = channel.execute_operate_action(store, action, rules.make_task("dev", 4))
    assert first["status"] == "observed"
    assert second["status"] == "observed"
    assert calls == [3]
    assert store.authority == before
    assert store.settled_effects[0]["effect_id"] == effect["effect_id"]


def test_run_boundary_rejects_forged_experience_before_dispatch(monkeypatch):
    task_id = "ad01-w0-dev-sw-00"
    real = {"observation_id": "obs-real", "task_id": task_id,
            "capability_id": "seed-sw-greedy", "verdict": "preserved"}
    forged = {**real, "verdict": "forged"}
    proposal = {"basis_references": [forged["observation_id"]],
                "question": "why did the observation change?",
                "next_action": {"kind": "diagnostic",
                                "diagnostic": "software",
                                "task_id": task_id},
                "requested_resources": {"diagnostic_queries": 1}}
    monkeypatch.setattr(
        trajectory, "_read_campaign",
        lambda dsn, cid: ({"0": {"observation": real}}, {}))
    monkeypatch.setattr(trajectory, "record_decision", lambda *args, **kwargs: None)
    monkeypatch.setattr(trajectory, "_learner_checkpoint_op", lambda *args: None)
    from experiments.ad01 import agenda_policy
    monkeypatch.setattr(agenda_policy, "_correction_rows", lambda *args: [])
    monkeypatch.setattr(
        agenda_policy.DecisionConsumer, "_note_refusal",
        lambda self, *args: {"status": "refused", "reason": args[1]["reason"],
                             "corrections": 0})
    _, episode, spend = trajectory._run_boundary(
        task_id, "seed-sw-greedy", {},
        seed_obs={"observation_id": "obs-seed", "task_id": task_id,
                  "capability_id": "seed-sw-greedy", "verdict": "unmeasured"},
        charter={"objective": "reduce the task"},
        boundary={"world": 0, "arm": "I", "seq": 1},
        experience={"observations": [real, forged]},
        state=None, propose=lambda *_: proposal,
        journal={"dsn": "unused", "cid": "ad01-w0-I-01"})
    assert spend == 0
    assert episode["disposition"] == "no-candidate"
    assert "forged experience" in episode["fallback_reason"]


def test_zero_budget_public_wrapper_preserves_typed_refusal():
    result = trajectory.dev_episode(
        "ad01-w0-dev-sw-00", "seed-sw-greedy", max_queries=0)
    assert result["fallback_reason"] == "zero-budget-probe"
    assert "study lineage is untouched" in result["fallback_detail"]


def test_public_improvement_probe_is_admitted_and_settled(tmp_path):
    store = _probe_store(tmp_path)
    package = store.active_package

    result = live.run_live_improve_round(
        store, rules.make_task("dev", 4), package, 1)

    assert result["observations"] == [{"x": 3, "y": [1, 0, 0, 1]}]
    assert store.pending_effects == []
    assert len(store.settled_effects) == 1
    observation = store.observations[0]
    assert observation["effect_id"] == store.settled_effects[0]["effect_id"]
    assert observation["operation_id"] == store.settled_effects[0][
        "expected_identity"]["operation_id"]
    assert store.settle(
        store.settled_effects[0]["effect_id"], observation) == \
        store.settled_effects[0]

    repeated = live.run_live_improve_round(
        store, rules.make_task("dev", 4), package, 1)
    assert repeated["candidate"]["package_digest"] == \
        result["candidate"]["package_digest"]
    assert len(store.settled_effects) == 1
    assert len(store.observations) == 1
    assert store.authority == {
        "queries_total": 16, "steps_total": 12,
        "queries_used": 1, "steps_used": 3,
        "queries_remaining": 15, "steps_remaining": 9}


def test_public_improvement_refuses_unbound_package(tmp_path):
    store = _probe_store(tmp_path)
    store._doc["active_package"] = None
    store.save()

    with pytest.raises(live.LiveRefused, match="bound"):
        live.run_live_improve_round(
            store, rules.make_task("dev", 4), channel.make_control("low"), 1)


def test_retention_refuses_authored_package(tmp_path):
    from experiments.ad01 import improve_channel
    control = improve_channel.make_control("low")
    store_path = tmp_path / "store.json"
    from experiments.ad01 import frontier as _frontier
    _frontier.create_store(
        store_path, namespace=_frontier.NAMESPACE,
        mission={"objective": "m", "environments": [{"split": "dev",
                                                     "seed": 1}]},
        authority={"queries": 16, "steps": 12})
    store = _frontier.FrontierStore(str(store_path))
    with pytest.raises(live.LiveRefused):
        live.retain_acquired(store, {**control,
                                     "origin": "authored-control"})


def test_parse_live_improver_rejects_non_step():
    with pytest.raises(live.LiveRefused):
        live.parse_live_improver('{"entry": "import os"}')


def test_parse_live_improver_accepts_valid_step():
    from experiments.ad01 import improve_channel
    text = json.dumps({"entry": improve_channel.IMPROVE_LOW_SOURCE})
    parsed = live.parse_live_improver(text)
    assert parsed["imp_digest"] == live.source_digest(
        improve_channel.IMPROVE_LOW_SOURCE)


def test_diagnose_construction_names_stage():
    from experiments.ad01 import construct
    diagnosis = live.diagnose_construction(
        construct.ConstructionFailed("gate failed", calls_made=1), 1)
    assert diagnosis["stage"] == "gate"


def test_freeze_e0_bounds(tmp_path):
    protocol = driver.freeze_e0(tmp_path)
    assert protocol["bounds"] == {"model_calls": 12, "repairs": 2,
                                  "retries_per_call": 3}
    assert protocol["freeze_digest"] == driver._digest(
        {k: v for k, v in protocol.items() if k != "freeze_digest"})


def test_freeze_e12_reserves(tmp_path):
    protocol = driver.freeze_e12(tmp_path)
    assert protocol["bounds"]["per_arm"]["P1"] == {"init": 18,
                                                  "repair": 2}
    assert protocol["bounds"]["per_arm"]["P2"] == {"init": 18,
                                                  "repair": 2}
    assert protocol["worst_case"] <= 80


def test_recompute_marks_unattributed_calls_incomplete(tmp_path):
    protocol = driver.freeze_e0(tmp_path)
    (tmp_path / "e0-run.json").write_text(json.dumps({
        "freeze_digest": protocol["freeze_digest"],
        "live": {"model_calls": 3}, "ledger": []}) + "\n")
    result = driver.recompute(tmp_path)
    assert result["status"] == "incomplete"
    assert result["problems"] == [
        "unattributed-model-calls e0-run.json claimed=3 attributed=0"]


def test_recompute_fails_tampered_freeze(tmp_path):
    driver.freeze_e0(tmp_path)
    freeze = json.loads((tmp_path / "freeze.json").read_text())
    freeze["bounds"]["model_calls"] = 999
    (tmp_path / "freeze.json").write_text(json.dumps(freeze) + "\n")
    (tmp_path / "e0-run.json").write_text(json.dumps(
        {"freeze_digest": "other", "live": {"model_calls": 1},
         "ledger": []}) + "\n")
    result = driver.recompute(tmp_path)
    assert result["status"] == "fail"
    assert "freeze-digest-mismatch" in result["problems"]


def test_recompute_flags_nonzero_cost(tmp_path):
    protocol = driver.freeze_e0(tmp_path)
    (tmp_path / "e0-run.json").write_text(json.dumps({
        "freeze_digest": protocol["freeze_digest"],
        "live": {"model_calls": 1},
        "ledger": [{"operation_id": "op-1",
                    "dispatch_evidence_digest": "a" * 64,
                    "usage": {"charge_units": 7}}]}) + "\n")
    result = driver.recompute(tmp_path)
    assert result["status"] == "fail"
    assert any(p.startswith("nonzero-cost") for p in result["problems"])


def test_recompute_accepts_attributed_error_and_zero_usage(tmp_path):
    protocol = driver.freeze_e0(tmp_path)
    (tmp_path / "e0-run.json").write_text(json.dumps({
        "freeze_digest": protocol["freeze_digest"],
        "live": {"model_calls": 2},
        "ledger": [
            {"operation_id": "op-err",
             "dispatch_evidence_digest": "a" * 64,
             "diagnosis": {"stage": "transport"}},
            {"operation_id": "op-ok",
             "dispatch_evidence_digest": "b" * 64,
             "usage": {"charge_units": 0, "billed": False}}]})
     + "\n")
    result = driver.recompute(tmp_path)
    assert result["status"] == "pass"
    assert result["problems"] == []
    assert result["recomputed"]["model_calls"] == 2
    assert result["recomputed"]["model_claimed"] == 2
    assert result["recomputed"]["ledger_entries"] == 2


def test_run_refuses_without_grant(tmp_path, monkeypatch):
    monkeypatch.delenv("S09_M5_LIVE_GRANT", raising=False)
    monkeypatch.delenv("INVL02_LIVE_GRANT", raising=False)
    driver.freeze_e0(tmp_path)
    with pytest.raises(ValueError):
        driver.run_e0("dsn", tmp_path)
