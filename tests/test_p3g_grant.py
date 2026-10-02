"""Pass-3 grant sweep (coord02): finite-grant enforcement end to end.

Covers the pass-2 closures (live-without-grant block, spend accounting)
plus siblings found here: malformed construction grants must refuse
instead of crashing preflight; live construction calls and live episode
model calls must pass the finite-grant preflight even when they bypass
the CLI entry; replay must not double-count construction spend.
"""

from __future__ import annotations

import os
import uuid

import pytest

from experiments.coord02 import entry
from experiments.coord02 import experience as E
from experiments.coord02 import preflight as P
from settlement import store
from settlement.common import Command
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

_LIVE_ENV = {"SETTLEMENT_GATEWAY_ENDPOINT": "http://localhost:6446/v1",
             "TEAM01_LIVE_API_KEY": "grant", "TEAM01_LIVE_MODEL": "m"}

_FULL_GRANT = {"EC02_LIVE_GRANT_EPISODES": "48",
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


def _live_env(monkeypatch):
    for var in _GRANT_VARS:
        monkeypatch.delenv(var, raising=False)
    for var, value in _LIVE_ENV.items():
        monkeypatch.setenv(var, value)


def _op(prefix: str) -> str:
    return "%s-%s" % (prefix, uuid.uuid4().hex[:12])


def _funded(dsn: str, tag: str) -> str:
    assert "live" not in dsn
    store.seed_grant(dsn, Command(
        request_id=_op("p3g-grant"), payload={
            "version": 1, "charter_text": "p3g",
            "authority_grant": {}, "envelopes": {}}))
    store.seed_allocation(dsn, Command(
        request_id=_op("p3g-alloc"), payload={
            "allocation_id": "%s-a" % tag, "domain": "cpu",
            "authorized": 100000, "max_occupancy": 16}))
    return "%s-a" % tag


def test_p3g_malformed_construction_grant_refuses():
    env = dict(_LIVE_ENV, EC02_LIVE_GRANT_EPISODES="144",
               EC02_LIVE_GRANT_CALLS="abc")
    verdict = P.preflight_live(env=env)
    assert verdict["admitted"] is False
    assert any("EC02_LIVE_GRANT_CALLS" in p for p in verdict["problems"])
    with pytest.raises(PermissionError):
        P.require_live(env=env)


def test_p3g_zero_construction_grant_refuses_default_demand():
    env = dict(_LIVE_ENV, EC02_LIVE_GRANT_EPISODES="144",
               EC02_LIVE_GRANT_CALLS="0")
    verdict = P.preflight_live(env=env)
    assert verdict["admitted"] is False


def test_p3g_entry_blocks_live_development_without_grant(
        monkeypatch, capsys):
    for var in _GRANT_VARS:
        monkeypatch.delenv(var, raising=False)
    rc = entry.main(["--panel", "development", "--model", "live-model",
                     "--dsn", "dbname=ec02test_p3g_unused"])
    assert rc == 2
    assert "blocked" in capsys.readouterr().out


def test_p3g_construction_ceiling_single_source():
    assert E.MAX_CONSTRUCTION_CALLS == P.CONSTRUCTION_CALLS == 4


def test_p3g_ledger_refuses_live_without_finite_grant(
        migrated_db, monkeypatch):
    dsn = migrated_db
    _live_env(monkeypatch)
    gw = StubLive()
    seed = E.seed_construction_campaign(
        dsn, "p3g-%s" % uuid.uuid4().hex[:8], E.construction_budget())
    ledger = E.ConstructionLedger(
        dsn, seed["allocation_id"],
        attempt_prefix="coord02-L-construct-p3g-%s" % uuid.uuid4().hex[:8])
    episodes = [{"task_id": "c02-t01",
                 "packet": {"probe_observations": [], "decisions": [],
                            "joins": [], "plans": [], "submissions": []}}]
    request = E.construction_request(
        episodes, E.construction_budget(), lineage=1, attempt="init")
    with pytest.raises(PermissionError):
        ledger.request_call(request, gateway=gw)
    assert gw.calls == []
    assert ledger.calls_used() == 0


def test_p3g_ledger_admits_live_with_full_grant(
        migrated_db, monkeypatch):
    dsn = migrated_db
    _live_env(monkeypatch)
    for var, value in _FULL_GRANT.items():
        monkeypatch.setenv(var, value)
    gw = StubLive('{"entry": "x = 1\\n"}')
    seed = E.seed_construction_campaign(
        dsn, "p3g-%s" % uuid.uuid4().hex[:8], E.construction_budget())
    ledger = E.ConstructionLedger(
        dsn, seed["allocation_id"],
        attempt_prefix="coord02-L-construct-p3g-%s" % uuid.uuid4().hex[:8])
    episodes = [{"task_id": "c02-t01",
                 "packet": {"probe_observations": [], "decisions": [],
                            "joins": [], "plans": [], "submissions": []}}]
    request = E.construction_request(
        episodes, E.construction_budget(), lineage=1, attempt="init")
    record = ledger.request_call(request, gateway=gw)
    assert record["live"] is True
    assert len(gw.calls) == 1
    assert ledger.accounting()["live_calls_used"] == 1


def test_p3g_ledger_replay_does_not_double_spend(migrated_db):
    dsn = migrated_db
    seed = E.seed_construction_campaign(
        dsn, "p3g-%s" % uuid.uuid4().hex[:8], E.construction_budget())
    ledger = E.ConstructionLedger(
        dsn, seed["allocation_id"],
        attempt_prefix="coord02-L-construct-p3g-%s" % uuid.uuid4().hex[:8])
    episodes = [{"task_id": "c02-t01",
                 "packet": {"probe_observations": [], "decisions": [],
                            "joins": [], "plans": [], "submissions": []}}]
    request = E.construction_request(
        episodes, E.construction_budget(), lineage=1, attempt="init")
    first = ledger.request_call(
        request, gateway=FakeGatewayAdapter(), replay=True)
    second = ledger.request_call(
        request, gateway=FakeGatewayAdapter(), replay=True)
    assert first["operation_id"] == second["operation_id"]
    assert ledger.calls_used() == 1


def test_p3g_child_dispatch_refuses_live_without_grant(
        migrated_db, monkeypatch):
    dsn = migrated_db
    _live_env(monkeypatch)
    alloc = _funded(dsn, "p3g-child-%s" % uuid.uuid4().hex[:8])
    gw = StubLive()
    with pytest.raises(PermissionError):
        entry.dispatch_admitted_child(
            dsn, gateway=gw, model="m", task_id="c02-t01", node="w1",
            child={"owned_paths": ["src/app.py"]}, rendered={},
            allocation_id=alloc, operation_id=_op("p3g-child"))
    assert gw.calls == []


def test_p3g_child_dispatch_doubled_needs_no_grant(migrated_db, monkeypatch):
    dsn = migrated_db
    for var in _GRANT_VARS:
        monkeypatch.delenv(var, raising=False)
    alloc = _funded(dsn, "p3g-child-%s" % uuid.uuid4().hex[:8])
    out = entry.dispatch_admitted_child(
        dsn, gateway=FakeGatewayAdapter(text=""), model="doubled",
        task_id="c02-t01", node="w1",
        child={"owned_paths": ["src/app.py"]}, rendered={},
        allocation_id=alloc, operation_id=_op("p3g-child"))
    assert out is None


def test_p3g_interpret_refuses_live_without_grant(
        migrated_db, monkeypatch):
    dsn = migrated_db
    _live_env(monkeypatch)
    alloc = _funded(dsn, "p3g-ainterp-%s" % uuid.uuid4().hex[:8])
    gw = StubLive()
    with pytest.raises(PermissionError):
        entry._interpret_with_model(
            gateway=gw, model="m", prompt="decide",
            operation_id=_op("p3g-a"), dsn=dsn, allocation_id=alloc)
    assert gw.calls == []


def test_p3g_interpret_live_admits_with_grant(
        migrated_db, monkeypatch):
    dsn = migrated_db
    _live_env(monkeypatch)
    for var, value in _FULL_GRANT.items():
        monkeypatch.setenv(var, value)
    alloc = _funded(dsn, "p3g-ainterp-%s" % uuid.uuid4().hex[:8])
    gw = StubLive()
    decided = entry._interpret_with_model(
        gateway=gw, model="m", prompt="decide",
        operation_id=_op("p3g-a"), dsn=dsn, allocation_id=alloc)
    assert decided["proposal"]["action"] == "unsupported"
    assert len(gw.calls) == 1
