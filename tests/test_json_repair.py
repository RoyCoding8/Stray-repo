"""JSON repair gates for invl02-json: strict boolean extraction.

Failing-first: each test demonstrates a lenient-parser or driver gap
before the fix, then locks the strict invariant after it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from experiments.ad01 import boolean_rule as rules
from experiments.ad01 import live_construct as live
from experiments.ad01 import rule_learner
from scripts import invl02_live as driver


class _ScriptGateway:
    def __init__(self, texts=None, error=None, usages=None):
        self.texts = list(texts or [])
        self.error = error
        self.usages = list(usages or [])
        self.requests = []

    def check_discovery(self):
        return "configured"

    def check_auth(self):
        return "authenticated"

    def cancel(self, operation_id):
        return True

    def infer(self, request):
        from settlement.gateway import ModelResponse, Usage
        self.requests.append(request)
        if self.error is not None:
            return self.error
        usage = self.usages.pop(0) if self.usages else Usage()
        return ModelResponse(request.operation_id, self.texts.pop(0),
                             {}, usage, "stop")


def _guard(texts=None, ceiling=12, usages=None, error=None):
    return live.LiveGuard(_ScriptGateway(texts, error=error,
                                         usages=usages),
                          pinned_model="test-model", ceiling=ceiling)


def _legal_specs_text(split="qual", seed=11):
    task = rules.make_task(split, seed)
    session = rules.RuleSession(task)
    learner = rule_learner.VersionSpaceLearner(rules.CLASS_TABLES, seed)
    while session.remaining > 0:
        pick = learner.choose_query(dict(session.queried))
        if pick is None:
            break
        found = session.query(pick)
        learner.observe(pick, found)
    legal = learner.predict(dict(session.queried))
    return json.dumps({"specs": [dict(s) for s in legal["specs"]]})


P1_MALFORMED = '{"specs": [{"const": 0 "mask": 8}]}'
P2_MALFORMED = "{'specs': [{'const': 0, 'mask': 8}]}"


def test_p1_delimiter_failure_repairs_inside_reserve():
    legal = _legal_specs_text()
    guard = _guard([P1_MALFORMED, legal], ceiling=12)
    result = driver.boolean_live_round(
        guard=guard, model="test-model", split="qual", seed=11,
        history=[], repairs=2)
    assert result["failed_attempts"] == 1
    assert result["model_calls"] == 2
    assert guard.dispatch_count == 2
    assert result["score"]["overall"] >= 0.0


def test_p2_single_quote_failure_repairs_inside_reserve():
    legal = _legal_specs_text()
    guard = _guard([P2_MALFORMED, legal], ceiling=12)
    result = driver.boolean_live_round(
        guard=guard, model="test-model", split="qual", seed=11,
        history=[], repairs=2)
    assert result["failed_attempts"] == 1
    assert result["model_calls"] == 2


def test_strict_schema_rejects_extra_top_level_key():
    legal = json.loads(_legal_specs_text())
    legal["extra"] = "leak"
    with pytest.raises(live.LiveRefused):
        live.extract_and_validate_boolean(json.dumps(legal))


def test_strict_schema_rejects_bool_const():
    legal = json.loads(_legal_specs_text())
    legal["specs"][0] = {"const": True, "mask": 8, "pair": None}
    with pytest.raises(live.LiveRefused):
        live.extract_and_validate_boolean(json.dumps(legal))


def test_fenced_block_extraction_ignores_trailing_brace_prose():
    legal = _legal_specs_text()
    text = ("Here is the predictor:\n```json\n%s\n```\n"
            "Hope this helps with } brace" % legal)
    payload = live.extract_and_validate_boolean(text)
    assert set(payload.keys()) == {"specs"}
    assert len(payload["specs"]) == 4


def test_bare_prose_wrapped_json_without_fence_is_refused():
    legal = _legal_specs_text()
    text = "Here is your predictor %s hope this helps" % legal
    with pytest.raises(live.LiveRefused):
        live.extract_and_validate_boolean(text)


def test_bounded_repairs_never_exceed_reserve():
    bad = ["not json at all"] * 10
    guard = _guard(bad, ceiling=12)
    with pytest.raises(ValueError):
        driver.boolean_live_round(
            guard=guard, model="test-model", split="qual", seed=11,
            history=[], repairs=2)
    assert guard.dispatch_count == 3


def test_probe_result_stamps_usage_explicitly():
    source = Path(driver.__file__).read_text()
    probe_body = source[source.index("def probe("):source.index(
        "def main(")]
    assert '"usage"' in probe_body or "'usage'" in probe_body
    assert "unknown" in probe_body


def test_recompute_enforces_ceiling_on_counted_dispatches(tmp_path):
    protocol = driver.freeze_e0(tmp_path)
    (tmp_path / "e0-run.json").write_text(json.dumps({
        "freeze_digest": protocol["freeze_digest"],
        "live": {"model_calls": 13},
        "guard": {"pinned_model": "m", "ceiling": 12,
                  "dispatch_count": 13, "refusal_reason": "",
                  "cost_blocked": None, "version": "invl02-live-v1"},
        "ledger": []}) + "\n")
    result = driver.recompute(tmp_path)
    assert result["status"] == "fail"
    assert any("ceiling" in p for p in result["problems"])


def test_recompute_counts_ledger_dispatches_not_claims(tmp_path):
    protocol = driver.freeze_e0(tmp_path)
    ledger = [{"operation_id": "op-%d" % i, "attempt": 1,
               "outcome": "text",
               "usage": {"input_tokens": 1, "output_tokens": 1,
                         "charge_units": 0, "billed": False}}
              for i in range(3)]
    (tmp_path / "e0-run.json").write_text(json.dumps({
        "freeze_digest": protocol["freeze_digest"],
        "live": {"model_calls": 1},
        "guard": {"pinned_model": "m", "ceiling": 12,
                  "dispatch_count": 3, "refusal_reason": "",
                  "cost_blocked": None, "version": "invl02-live-v1"},
        "ledger": ledger}) + "\n")
    result = driver.recompute(tmp_path)
    assert result["status"] == "fail"
    assert any("dispatch" in p for p in result["problems"])


def test_guard_splits_cost_from_ceiling_predicates():
    from settlement.gateway import GatewayError, GatewayErrorKind, \
        ModelRequest, Usage
    assert hasattr(live.LiveGuard, "is_cost_blocked")
    assert hasattr(live.LiveGuard, "is_ceiling_reached")
    error = GatewayError(GatewayErrorKind.TRANSPORT, "boom", False,
                         "op-1", Usage(charge_units=5))
    cost_guard = _guard(error=None, ceiling=12)
    cost_guard.delegate.error = error
    cost_guard.infer(ModelRequest(model="test-model", messages=(),
                                  max_output_tokens=8, deadline_ms=1000,
                                  operation_id="op-1"))
    assert cost_guard.is_cost_blocked() is True
    assert cost_guard.is_ceiling_reached() is False
    assert cost_guard.guard_status()["refusal_kind"] == "cost"
    ceiling_guard = live.LiveGuard(
        _ScriptGateway(["hi"]), pinned_model="test-model",
        ceiling=1, already_spent=1)
    assert ceiling_guard.is_ceiling_reached() is True
    assert ceiling_guard.is_cost_blocked() is False
    with pytest.raises(live.LiveRefused):
        ceiling_guard.infer(ModelRequest(
            model="test-model", messages=(), max_output_tokens=8,
            deadline_ms=1000, operation_id="op-1"))
    assert ceiling_guard.guard_status()["refusal_kind"] == "ceiling"


def test_freeze_output_bounds(tmp_path):
    protocol = driver.freeze_output(tmp_path)
    assert protocol["limits"]["max_dispatches"] == 8
    assert protocol["limits"]["max_output_tokens"] == 2048
    assert protocol["limits"]["automatic_retries"] == 0
    assert protocol["limits"]["repairs_per_task"] == 1
    assert protocol["freeze_digest"] == driver._digest(
        {k: v for k, v in protocol.items() if k != "freeze_digest"})


def test_output_run_counts_repairs_with_new_operation_ids(tmp_path):
    protocol = driver.freeze_output(tmp_path)
    legal_p1 = _legal_specs_text("qual", 11)
    guard = _guard([P1_MALFORMED, legal_p1], ceiling=8)
    out = driver.boolean_live_round(
        guard=guard, model="test-model", split="qual", seed=11,
        history=[], repairs=1, max_output_tokens=2048)
    assert out["failed_attempts"] == 1
    assert guard.dispatch_count == 2
    assert guard.ledger[0]["operation_id"] != guard.ledger[1]["operation_id"]
    assert protocol["limits"]["max_dispatches"] == 8
