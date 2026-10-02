"""Durable broker ownership for the E4 model acquisition seam."""

from __future__ import annotations

import json
import uuid

import pytest

from experiments.ad01 import learner_revision as lr
from settlement import broker, store
from settlement.common import Command, ResultCode
from settlement.gateway import ModelResponse, Usage


def _cmd(tag: str, payload: dict) -> Command:
    return Command(request_id="%s-%s" % (tag, uuid.uuid4().hex), payload=payload)


def _seed(dsn: str, tag: str, *, authorized: int = 10_000) -> dict:
    allocation_id = "%s-allocation" % tag
    investigation_id = "%s-investigation" % tag
    attempt_id = "%s-attempt" % tag
    assert store.seed_allocation(
        dsn, _cmd(tag, {"allocation_id": allocation_id, "domain": "model",
                        "authorized": authorized})).code == ResultCode.APPLIED
    assert store.admit_commitment(
        dsn, _cmd(tag, {"investigation_id": investigation_id,
                        "objective": "E4 accounting"})).code == ResultCode.APPLIED
    acquired = store.acquire_work(
        dsn, _cmd(tag, {"attempt_id": attempt_id,
                        "investigation_id": investigation_id,
                        "allocation_id": allocation_id,
                        "model": "fixture-model"}))
    assert acquired.code == ResultCode.APPLIED
    return {"allocation_id": allocation_id, "attempt_id": attempt_id}


def _route(provider: str = "Fixture") -> dict:
    return {"endpoint": "http://fixture.invalid", "provider": provider,
            "tier": "free", "requested_model": "fixture-model",
            "resolved_model": "fixture-model"}


def _live(dsn: str, seed: dict, namespace: str,
          route: dict | None = None) -> lr.LiveAcquisition:
    route = route or _route()
    return lr.LiveAcquisition(
        dsn=dsn, allocation_id=seed["allocation_id"],
        attempt_id=seed["attempt_id"], operation_namespace=namespace,
        environ={"SETTLEMENT_EXPECTED_ROUTE": json.dumps(route),
                  "INVL02_LIVE_MODEL": "fixture-model"})


def _messages() -> list[dict[str, str]]:
    return [{"role": "user", "content": "return a STEP function"}]


def _valid_reply() -> str:
    return lr.channel._revision_source("7").replace(
        '"x": 7', '"x": 7 if not view["experience"] else 3', 1)


class FixtureGateway:
    def __init__(self, *, lost: bool = False, text: str = "candidate"):
        self.lost = lost
        self.text = text
        self.calls = []

    def infer(self, request):
        self.calls.append(request)
        if self.lost:
            return None
        return ModelResponse(
            operation_id=request.operation_id, text=self.text,
            model_meta={"fixture": True},
            usage=Usage(input_tokens=2, output_tokens=3), stop_reason="stop")


def _patch_gateway(monkeypatch, gateway: FixtureGateway) -> None:
    from settlement import gateway_http

    monkeypatch.setattr(
        gateway_http, "HttpGatewayAdapter",
        lambda **_kwargs: gateway)


def test_success_settles_and_replay_reads_one_durable_receipt(
        migrated_db, monkeypatch):
    seed = _seed(migrated_db, "success")
    gateway = FixtureGateway()
    _patch_gateway(monkeypatch, gateway)
    live = _live(migrated_db, seed, "e4-success")

    first = live.dispatch(1, _messages(), max_output_tokens=16,
                          timeout_total_ms=60_000)
    assert first.reply == "candidate" and not first.error
    assert len(gateway.calls) == 1
    row = broker.read_operation(migrated_db, first.operation_id)
    assert row["dispatch_state"] == "observed"
    receipts = store.operation_receipts(migrated_db, first.operation_id)
    assert len(receipts) == 1
    assert receipts[0]["outcome"] == "success"
    assert first.durable_receipt["receipt_identity"] == (
        "gw:%s" % first.operation_id)
    assert first.durable_receipt["provenance"] == "gateway"
    assert first.durable_receipt["content"]["operation_id"] == first.operation_id
    assert first.durable_receipt["content"]["model_meta"] == {"fixture": True}
    assert first.dispatch_state == "observed"
    assert first.settled is True
    settled = store.allocation_status(migrated_db, seed["allocation_id"])
    assert settled["reserved"] == 0

    replay = live.dispatch(1, _messages(), max_output_tokens=16,
                           timeout_total_ms=60_000)
    assert replay.reply == "candidate" and not replay.error
    assert len(gateway.calls) == 1
    assert store.allocation_status(migrated_db, seed["allocation_id"]) == settled

    changed = live.dispatch(
        1, [{"role": "user", "content": "a different prompt"}],
        max_output_tokens=16, timeout_total_ms=60_000)
    assert "operation admission refused" in changed.error
    assert len(gateway.calls) == 1


def test_route_drift_refuses_same_operation_before_gateway_inference(
        migrated_db, monkeypatch):
    seed = _seed(migrated_db, "route-drift")
    gateway = FixtureGateway()
    _patch_gateway(monkeypatch, gateway)
    first_live = _live(migrated_db, seed, "e4-route-drift")
    first = first_live.dispatch(1, _messages(), max_output_tokens=16,
                                timeout_total_ms=60_000)
    assert not first.error

    changed_live = _live(migrated_db, seed, "e4-route-drift",
                          route=_route("OtherFixture"))
    changed = changed_live.dispatch(1, _messages(), max_output_tokens=16,
                                    timeout_total_ms=60_000)
    assert "operation admission refused" in changed.error
    assert changed.durable_receipt is None
    assert len(gateway.calls) == 1
    row = broker.read_operation(migrated_db, first.operation_id)
    assert row["execution_version"] == lr._route_execution_version(_route())


def test_pre_recorded_non_gateway_receipt_is_not_live_attributable(
        migrated_db, monkeypatch):
    seed = _seed(migrated_db, "recorded-receipt")
    gateway = FixtureGateway()
    _patch_gateway(monkeypatch, gateway)
    live = _live(migrated_db, seed, "e4-recorded-receipt")
    operation_id = "e4-recorded-receipt-revision-0001"
    payload = {"model": live.model, "messages": _messages(),
               "max_output_tokens": 16, "deadline_ms": 55_000,
               "reasoning_effort": None}
    prepared = broker.ensure_operation(
        migrated_db, operation_id=operation_id,
        effect=broker.MODEL_INFERENCE, payload=payload,
        allocation_id=seed["allocation_id"], attempt_id=seed["attempt_id"],
        execution_version=lr._route_execution_version(_route()),
        resource="model_calls")
    assert prepared.code == ResultCode.APPLIED
    advanced = broker._advance(migrated_db, operation_id, "gateway",
                               live.model, None, None)
    assert advanced.code == ResultCode.APPLIED
    admitted = broker.admit_launcher_receipt(
        migrated_db, operation_id,
        broker.ReceiptProposal(
            receipt_identity="recorded:%s" % operation_id,
            content={"operation_id": operation_id, "text": "candidate",
                     "model_meta": {"fixture": True},
                     "usage": {"input_tokens": 2, "output_tokens": 3}},
            outcome="success", provenance="recorded-double"))
    assert admitted.code == ResultCode.APPLIED

    result = live.dispatch(1, _messages(), max_output_tokens=16,
                           timeout_total_ms=60_000)
    assert "identity/provenance mismatch" in result.error
    assert result.durable_receipt["provenance"] == "recorded-double"
    assert gateway.calls == []


@pytest.mark.parametrize("lost", [False, True])
def test_campaign_export_links_durable_success_or_lost_receipt(
        migrated_db, monkeypatch, tmp_path, lost):
    seed = _seed(migrated_db, "campaign-export-%s" % lost)
    gateway = FixtureGateway(lost=lost, text=_valid_reply())
    _patch_gateway(monkeypatch, gateway)
    monkeypatch.setenv("SETTLEMENT_EXPECTED_ROUTE", json.dumps(_route()))
    monkeypatch.setenv("INVL02_LIVE_MODEL", "fixture-model")

    campaign = lr.run_campaign(
        workdir=tmp_path / ("campaign-%s" % lost), dsn=migrated_db,
        allocation_id=seed["allocation_id"], attempt_id=seed["attempt_id"],
        operation_namespace="e4-export-%s" % lost, attempts=1,
        cohort=[0])
    [dispatch] = campaign["dispatches"]
    receipt = dispatch["durable_receipt"]
    assert receipt["operation_id"] == dispatch["operation_id"]
    assert receipt["provenance"] == "gateway"
    assert receipt["content"]["operation_id"] == dispatch["operation_id"]
    if lost:
        assert receipt["outcome"] == "unknown"
        assert receipt["usage"] is None
        assert dispatch["usage"] is None
        assert receipt["unresolved_exposure"] == receipt["exposure"] > 0
        assert dispatch["dispatch_state"] == "unresolved"
        assert dispatch["settled"] is False
    else:
        assert receipt["outcome"] == "success"
        assert receipt["content"]["model_meta"] == {"fixture": True}
        assert receipt["usage"]["input_tokens"] == 2
        assert receipt["unresolved_exposure"] == 0
        assert dispatch["dispatch_state"] == "observed"
        assert dispatch["settled"] is True
    if lost:
        claim = dict(dispatch, acquisition=lr.ACQUIRED, eligible=True,
                     reply="", source_digest="response-source")
        assert not lr.live_attributable({"dispatches": [claim]})
    else:
        assert dispatch["acquisition"] == lr.ACQUIRED
        claim = dict(dispatch, eligible=True)
        assert lr.live_attributable({"dispatches": [claim]})
        altered = dict(claim, source_digest="0" * 64)
        assert not lr.live_attributable({"dispatches": [altered]})
    assert len(gateway.calls) == 1


def test_campaign_namespace_keeps_operation_identities_distinct(
        migrated_db, monkeypatch):
    seed = _seed(migrated_db, "namespaces")
    gateway = FixtureGateway()
    _patch_gateway(monkeypatch, gateway)

    first = _live(migrated_db, seed, "e4-campaign-a").dispatch(
        1, _messages(), max_output_tokens=16, timeout_total_ms=60_000)
    second = _live(migrated_db, seed, "e4-campaign-b").dispatch(
        1, _messages(), max_output_tokens=16, timeout_total_ms=60_000)

    assert first.operation_id != second.operation_id
    assert len(gateway.calls) == 2
    assert all(broker.read_operation(migrated_db, op)["dispatch_state"] == "observed"
               for op in (first.operation_id, second.operation_id))


def test_unbound_allocation_is_refused_before_gateway_inference(
        migrated_db, monkeypatch):
    seed = _seed(migrated_db, "unbound")
    gateway = FixtureGateway()
    _patch_gateway(monkeypatch, gateway)
    live = lr.LiveAcquisition(
        dsn=migrated_db, allocation_id="missing-allocation",
        attempt_id=seed["attempt_id"], operation_namespace="e4-unbound",
        environ={"SETTLEMENT_EXPECTED_ROUTE": json.dumps({
            "endpoint": "http://fixture.invalid", "provider": "Fixture",
            "tier": "free", "requested_model": "fixture-model",
            "resolved_model": "fixture-model"}),
                  "INVL02_LIVE_MODEL": "fixture-model"})

    result = live.dispatch(1, _messages(), max_output_tokens=16,
                           timeout_total_ms=60_000)
    assert "operation admission refused" in result.error
    assert result.durable_receipt is None
    assert result.dispatch_state is None
    assert gateway.calls == []
    assert broker.read_operation(migrated_db, result.operation_id) is None


def test_durable_model_call_reservation_refuses_next_distinct_operation(
        migrated_db, monkeypatch):
    seed = _seed(migrated_db, "model-cap", authorized=2)
    gateway = FixtureGateway()
    _patch_gateway(monkeypatch, gateway)
    live = _live(migrated_db, seed, "e4-model-cap")
    tiny = [{"role": "user", "content": "x"}]

    first = live.dispatch(1, tiny, max_output_tokens=1,
                          timeout_total_ms=60_000)
    second = live.dispatch(2, tiny, max_output_tokens=1,
                           timeout_total_ms=60_000)

    assert first.reply == "candidate"
    assert "operation admission refused" in second.error
    assert len(gateway.calls) == 1
    assert broker.read_operation(migrated_db, first.operation_id)["payload"][
        "resource"] == "model_calls"
    assert broker.read_operation(migrated_db, second.operation_id) is None


def test_lost_response_keeps_unknown_receipt_and_exposure_on_replay(
        migrated_db, monkeypatch):
    seed = _seed(migrated_db, "lost")
    gateway = FixtureGateway(lost=True)
    _patch_gateway(monkeypatch, gateway)
    live = _live(migrated_db, seed, "e4-lost")

    first = live.dispatch(1, _messages(), max_output_tokens=16,
                          timeout_total_ms=60_000)
    assert "lost-response" in first.error
    assert len(gateway.calls) == 1
    row = broker.read_operation(migrated_db, first.operation_id)
    assert row["dispatch_state"] == "unresolved"
    assert row["reconcile_state"] == "unresolved"
    [receipt] = store.operation_receipts(migrated_db, first.operation_id)
    assert receipt["outcome"] == "unknown"
    assert receipt["content"]["operation_id"] == first.operation_id
    assert receipt["provenance"] == "gateway"
    assert receipt["content"]["response_class"] == "lost-response"
    assert store.allocation_status(migrated_db, seed["allocation_id"])[
        "reserved"] > 0

    replay = live.dispatch(1, _messages(), max_output_tokens=16,
                           timeout_total_ms=60_000)
    assert "lost-response" in replay.error
    assert len(gateway.calls) == 1


def test_missing_receipt_is_reported_without_reinference(
        migrated_db, monkeypatch):
    seed = _seed(migrated_db, "missing-receipt")
    gateway = FixtureGateway()
    _patch_gateway(monkeypatch, gateway)
    live = _live(migrated_db, seed, "e4-missing-receipt")
    first = live.dispatch(1, _messages(), max_output_tokens=16,
                          timeout_total_ms=60_000)
    assert len(gateway.calls) == 1

    from settlement import db
    with db.connect(migrated_db) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM receipts WHERE operation_id = %s",
                        (first.operation_id,))
        conn.commit()

    replay = live.dispatch(1, _messages(), max_output_tokens=16,
                           timeout_total_ms=60_000)
    assert "missing durable receipt" in replay.error
    assert len(gateway.calls) == 1
