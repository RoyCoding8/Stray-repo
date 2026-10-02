from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from settlement import api, store
from settlement.common import Command, ResultCode


def _cmd(payload: dict, **kw) -> Command:
    return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload, **kw)


def _applied(result) -> None:
    """Fail the setup step that produced ``result`` if the store refused it.

    Without this the fixture returned an operation the commands act on and a
    refusal was indistinguishable from a command that could not find its
    target: `prepare_operation` was called without the `allocation_id`
    `acquire_work` had bound to the attempt, the store refused with
    `attempt w1 requires its bound allocation`, the fixture discarded the
    result, and `/commands/cancel` then answered `unknown operation op1`.
    """
    assert result.code == ResultCode.APPLIED, f"{result.code}: {result.detail}"


def _seeded_client(dsn: str, gateway=None) -> TestClient:
    """The one setup both cancel tests need, with every setup step checked."""
    _applied(store.seed_allocation(
        dsn, _cmd({"allocation_id": "a1", "domain": "cpu", "authorized": 100})))
    _applied(store.admit_commitment(dsn, _cmd({"investigation_id": "i1", "objective": "o"})))
    _applied(store.acquire_work(dsn, _cmd({"attempt_id": "w1", "investigation_id": "i1",
                                           "allocation_id": "a1"})))
    _applied(store.prepare_operation(dsn, _cmd({"operation_id": "op1", "attempt_id": "w1",
                                                "allocation_id": "a1",
                                                "operation": {"effect": "note"}})))
    app = api.create_app(dsn, gateway=gateway, token="test-token")
    return TestClient(app, headers={"x-operator-token": "test-token"})


@pytest.fixture()
def client(migrated_db):
    return _seeded_client(migrated_db)


def test_command_idempotency_same_id_twice(client):
    first = client.post("/commands/pause", data={"request_id": "p1", "attempt_id": "w1"}).text
    second = client.post("/commands/pause", data={"request_id": "p1", "attempt_id": "w1"}).text
    assert "accepted" in first and "applied" in first
    assert "already_applied" in second


def test_command_id_reuse_with_different_payload_is_refused(client):
    client.post("/commands/pause", data={"request_id": "p1", "attempt_id": "w1"})
    body = client.post("/commands/pause",
                       data={"request_id": "p1", "attempt_id": "w1", "ownership_generation": "9"}).text
    assert "refused" in body and "conflict-payload" in body


def test_pause_resume_cancel_cycle_with_external_unknown(client):
    assert "accepted" in client.post("/commands/pause",
                                     data={"attempt_id": "w1"}).text
    assert "accepted" in client.post("/commands/resume",
                                     data={"attempt_id": "w1"}).text
    body = client.post("/commands/cancel", data={"operation_id": "op1"}).text
    assert "accepted" in body
    assert "external outcome unknown" in body


def test_quarantine_degrades_cleanly_without_t5(client, monkeypatch):
    import sys

    import settlement.capabilities  # noqa: F401  (prove the slice exists here)

    monkeypatch.setitem(sys.modules, "settlement.capabilities", None)
    body = client.post("/commands/quarantine", data={"subject": "cap-v9"}).text
    assert "refused" in body and "unavailable_dependency" in body


def test_amend_allocation_and_repair_scan(client):
    amend = client.post("/commands/amend-allocation",
                        data={"allocation_id": "a1", "authorized": "150"}).text
    assert "accepted" in amend and "applied" in amend
    repair = client.post("/commands/repair", data={}).text
    assert "accepted" in repair


def test_inspect_unknown_operation_is_refused(client):
    body = client.post("/commands/inspect", data={"operation_id": "nope"}).text
    assert "refused" in body


def test_cancel_forwards_to_gateway(migrated_db):
    calls: list[str] = []

    class RecordingGateway:
        def cancel(self, operation_id: str) -> bool:
            calls.append(operation_id)
            return True

    client = _seeded_client(migrated_db, gateway=RecordingGateway())
    body = client.post("/commands/cancel", data={"operation_id": "op1"}).text
    assert "accepted" in body
    assert calls == ["op1"]
