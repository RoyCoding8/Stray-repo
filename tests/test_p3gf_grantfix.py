"""Grant-gate regression: recording/fake doubles run grant-free.

A labeled model-seam double with a recording/double model name must not
demand a live grant; an unlabeled live-capable gateway still must, even
with no live env configured (capability-not-key gating intact).
"""

from __future__ import annotations

import uuid

import pytest

from experiments.coord02 import entry
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


class RecordingDouble(GatewayAdapter):
    label = "P3GF-RECORDING-DOUBLE"

    def __init__(self):
        self.calls: list = []

    def check_discovery(self):
        return GatewayStatus.CONFIGURED

    def check_auth(self):
        return GatewayStatus.AUTHENTICATED

    def infer(self, request):
        self.calls.append(request)
        return ModelResponse(request.operation_id, "",
                             {"recording-double": True},
                             Usage(input_tokens=7, output_tokens=3), "stop")

    def cancel(self, operation_id):
        return False


class UnlabeledLiveStandin(GatewayAdapter):
    def __init__(self):
        self.calls: list = []

    def check_discovery(self):
        return GatewayStatus.CONFIGURED

    def check_auth(self):
        return GatewayStatus.AUTHENTICATED

    def infer(self, request):
        self.calls.append(request)
        return ModelResponse(request.operation_id, "",
                             {},
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
        request_id=_op("p3gf-grant"), payload={
            "version": 1, "charter_text": "p3gf",
            "authority_grant": {}, "envelopes": {}}))
    store.seed_allocation(dsn, Command(
        request_id=_op("p3gf-alloc"), payload={
            "allocation_id": "%s-a" % tag, "domain": "cpu",
            "authorized": 100000, "max_occupancy": 16}))
    return "%s-a" % tag


def test_p3gf_fake_gateway_needs_no_grant(monkeypatch):
    _clear_env(monkeypatch)
    assert entry._is_live_gateway(FakeGatewayAdapter()) is False
    assert entry._is_live_gateway(None) is False
    entry._require_live_spend(FakeGatewayAdapter(), "doubled")


def test_p3gf_recording_double_needs_no_grant(monkeypatch):
    _clear_env(monkeypatch)
    gw = RecordingDouble()
    assert entry._is_live_gateway(gw, "recording") is False
    entry._require_live_spend(gw, "recording")


def test_p3gf_unlabeled_live_gateway_still_blocked_without_env(monkeypatch):
    _clear_env(monkeypatch)
    gw = UnlabeledLiveStandin()
    assert entry._is_live_gateway(gw, "m") is True
    with pytest.raises(PermissionError):
        entry._require_live_spend(gw, "m")
    assert gw.calls == []


def test_p3gf_interpret_with_recording_double_needs_no_grant(
        migrated_db, monkeypatch):
    dsn = migrated_db
    _clear_env(monkeypatch)
    alloc = _funded(dsn, "p3gf-rec-%s" % uuid.uuid4().hex[:8])
    gw = RecordingDouble()
    decided = entry._interpret_with_model(
        gateway=gw, model="recording", prompt="decide",
        operation_id=_op("p3gf-a"), dsn=dsn, allocation_id=alloc)
    assert decided["proposal"]["action"] == "unsupported"
    assert len(gw.calls) == 1


def test_p3gf_child_dispatch_with_double_model_needs_no_grant(
        migrated_db, monkeypatch):
    dsn = migrated_db
    _clear_env(monkeypatch)
    alloc = _funded(dsn, "p3gf-child-%s" % uuid.uuid4().hex[:8])
    out = entry.dispatch_admitted_child(
        dsn, gateway=RecordingDouble(), model="bdr02-resume-double",
        task_id="c02-t01", node="w1",
        child={"owned_paths": ["src/app.py"]}, rendered={},
        allocation_id=alloc, operation_id=_op("p3gf-child"))
    assert out is None
