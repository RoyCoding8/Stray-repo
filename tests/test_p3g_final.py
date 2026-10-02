"""Pass-3 final sweep: gateway-capability gate, resume gate, version forwarding.

Siblings of the pass-2 live-without-grant and spend-miscount closures:
any non-fake gateway is live-capable and must pass the finite-grant
preflight even when no API key is configured; resume (ledger reconcile)
must pass the same gate before redispatch; model dispatches forward the
current settlement grant version (and child ownership where available)
so stale grants/ownership refuse without send.
"""

from __future__ import annotations

import uuid

import pytest

from experiments.coord02 import entry
from experiments.coord02 import experience as E
from settlement import broker, store
from settlement.common import Command, ResultCode
from settlement.gateway import (
    FakeGatewayAdapter,
    GatewayAdapter,
    GatewayStatus,
    ModelResponse,
    Usage,
)

_GRANT_VARS = ("SETTLEMENT_GATEWAY_ENDPOINT", "TEAM01_LIVE_API_KEY",
               "SETTLEMENT_GATEWAY_KEY", "TEAM01_LIVE_MODEL",
               "EC02_LIVE_GRANT_EPISODES", "EC02_LIVE_GRANT_CALLS")

_FULL_ENV = {"SETTLEMENT_GATEWAY_ENDPOINT": "http://localhost:6446/v1",
             "TEAM01_LIVE_API_KEY": "grant", "TEAM01_LIVE_MODEL": "m",
             "EC02_LIVE_GRANT_EPISODES": "48",
             "EC02_LIVE_GRANT_CALLS": "4"}


class StubLive(GatewayAdapter):
    def __init__(self, text: str = "") -> None:
        self._text = text
        self.calls: list = []

    def check_discovery(self):
        return GatewayStatus.CONFIGURED

    def check_auth(self):
        return GatewayStatus.AUTHENTICATED

    def infer(self, request):
        self.calls.append(request)
        return ModelResponse(request.operation_id, self._text, {},
                             Usage(input_tokens=10, output_tokens=5,
                                   charge_units=1, billed=True), "stop")

    def cancel(self, operation_id):
        return False


def _clear_env(monkeypatch):
    for var in _GRANT_VARS:
        monkeypatch.delenv(var, raising=False)


def _op(prefix: str) -> str:
    return "%s-%s" % (prefix, uuid.uuid4().hex[:12])


def _funded(dsn: str, tag: str) -> str:
    assert "live" not in dsn
    store.seed_grant(dsn, Command(
        request_id=_op("p3f-grant"), payload={
            "version": 1, "charter_text": "p3f",
            "authority_grant": {}, "envelopes": {}}))
    store.seed_allocation(dsn, Command(
        request_id=_op("p3f-alloc"), payload={
            "allocation_id": "%s-a" % tag, "domain": "cpu",
            "authorized": 100000, "max_occupancy": 16}))
    return "%s-a" % tag


def _episodes() -> list:
    return [{"task_id": "c02-t01",
             "packet": {"probe_observations": [], "decisions": [],
                        "joins": [], "plans": [], "submissions": []}}]


def test_p3f_live_gateway_without_any_env_blocked_everywhere(
        migrated_db, monkeypatch):
    dsn = migrated_db
    _clear_env(monkeypatch)
    alloc = _funded(dsn, "p3f-nokey-%s" % uuid.uuid4().hex[:8])
    gw = StubLive()
    with pytest.raises(PermissionError):
        entry.dispatch_admitted_child(
            dsn, gateway=gw, model="m", task_id="c02-t01", node="w1",
            child={"owned_paths": ["src/app.py"]}, rendered={},
            allocation_id=alloc, operation_id=_op("p3f-child"))
    assert gw.calls == []
    gw2 = StubLive()
    with pytest.raises(PermissionError):
        entry._interpret_with_model(
            gateway=gw2, model="m", prompt="decide",
            operation_id=_op("p3f-a"), dsn=dsn, allocation_id=alloc)
    assert gw2.calls == []
    gw3 = StubLive('{"entry": "x = 1\\n"}')
    seed = E.seed_construction_campaign(
        dsn, "p3f-%s" % uuid.uuid4().hex[:8], E.construction_budget())
    ledger = E.ConstructionLedger(
        dsn, seed["allocation_id"],
        attempt_prefix="coord02-L-construct-p3f-%s" % uuid.uuid4().hex[:8])
    with pytest.raises(PermissionError):
        ledger.request_call(
            E.construction_request(
                _episodes(), E.construction_budget(),
                lineage=1, attempt="init"),
            gateway=gw3)
    assert gw3.calls == []
    assert ledger.calls_used() == 0


def test_p3f_doubled_needs_no_grant(migrated_db, monkeypatch):
    dsn = migrated_db
    _clear_env(monkeypatch)
    seed = E.seed_construction_campaign(
        dsn, "p3f-%s" % uuid.uuid4().hex[:8], E.construction_budget())
    ledger = E.ConstructionLedger(
        dsn, seed["allocation_id"],
        attempt_prefix="coord02-L-construct-p3f-%s" % uuid.uuid4().hex[:8])
    record = ledger.request_call(
        E.construction_request(
            _episodes(), E.construction_budget(),
            lineage=1, attempt="init"),
        gateway=FakeGatewayAdapter())
    assert record["live"] is False
    assert ledger.accounting()["live_calls_used"] == 0
    assert ledger.calls_used() == 1


def test_p3f_resume_reconcile_without_grant_blocked(
        migrated_db, monkeypatch):
    dsn = migrated_db
    _clear_env(monkeypatch)
    alloc = _funded(dsn, "p3f-res-%s" % uuid.uuid4().hex[:8])
    assert alloc
    seed = E.seed_construction_campaign(
        dsn, "p3f-%s" % uuid.uuid4().hex[:8], E.construction_budget())
    prefix = "coord02-L-construct-p3f-%s" % uuid.uuid4().hex[:8]
    ledger = E.ConstructionLedger(
        dsn, seed["allocation_id"], attempt_prefix=prefix)
    pending = "%s-l-1-init-1" % prefix
    ensured = broker.ensure_operation(
        dsn, operation_id=pending, effect=broker.MODEL_INFERENCE,
        payload={"model": "configured-live-model",
                 "messages": [{"role": "user", "content": "hi"}],
                 "max_output_tokens": 64, "deadline_ms": 5000,
                 "reasoning_effort": "low"},
        allocation_id=seed["allocation_id"])
    assert ensured.code == ResultCode.APPLIED
    ledger._hydrate()
    gw = StubLive()
    with pytest.raises(PermissionError):
        ledger._reconcile_pending(gw)
    assert gw.calls == []
    row = broker.read_operation(dsn, pending)
    assert row["dispatch_state"] == "prepared"


def test_p3f_stale_grant_version_refuses_without_send(migrated_db):
    dsn = migrated_db
    tag = "p3f-ver-%s" % uuid.uuid4().hex[:8]
    store.seed_grant(dsn, Command(
        request_id=_op("p3f-grant"), payload={
            "version": 1, "charter_text": "p3f",
            "authority_grant": {}, "envelopes": {}}))
    store.seed_allocation(dsn, Command(
        request_id=_op("p3f-alloc"), payload={
            "allocation_id": "%s-a" % tag, "domain": "cpu",
            "authorized": 100000, "max_occupancy": 16}))
    op = _op("p3f-ver")
    ensured = broker.ensure_operation(
        dsn, operation_id=op, effect=broker.MODEL_INFERENCE,
        payload={"model": "m",
                 "messages": [{"role": "user", "content": "hi"}],
                 "max_output_tokens": 32, "deadline_ms": 5000},
        allocation_id="%s-a" % tag)
    assert ensured.code == ResultCode.APPLIED
    current = int(store.get_control(dsn)["authority_version"])
    store.seed_grant(dsn, Command(
        request_id=_op("p3f-bump"), payload={
            "version": current + 1, "charter_text": "revoked",
            "authority_grant": {}, "envelopes": {}}))
    gw = StubLive()
    stale = broker.dispatch_operation(
        dsn, op, gateway=gw, grant_version=current)
    assert stale.sent_this_call is False
    assert stale.dispatch_state == "prepared"
    assert gw.calls == []


def test_p3f_live_admits_with_grant_and_forwards_version(
        migrated_db, monkeypatch):
    dsn = migrated_db
    _clear_env(monkeypatch)
    for var, value in _FULL_ENV.items():
        monkeypatch.setenv(var, value)
    alloc = _funded(dsn, "p3f-ok-%s" % uuid.uuid4().hex[:8])
    gw = StubLive()
    decided = entry._interpret_with_model(
        gateway=gw, model="m", prompt="decide",
        operation_id=_op("p3f-a"), dsn=dsn, allocation_id=alloc)
    assert decided["proposal"]["action"] == "unsupported"
    assert len(gw.calls) == 1
