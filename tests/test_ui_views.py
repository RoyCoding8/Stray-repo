from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from settlement import api, store
from settlement.common import Command


def _cmd(payload: dict, **kw) -> Command:
    return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload, **kw)


@pytest.fixture()
def client(migrated_db):
    dsn = migrated_db
    store.seed_allocation(dsn, _cmd({"allocation_id": "a1", "domain": "cpu", "authorized": 100}))
    store.admit_commitment(dsn, _cmd({"investigation_id": "i1",
                                      "objective": "<script>alert('x')</script>"}))
    store.acquire_work(dsn, _cmd({"attempt_id": "w1", "investigation_id": "i1",
                                  "allocation_id": "a1"}))
    store.prepare_operation(dsn, _cmd({"operation_id": "op1", "attempt_id": "w1",
                                       "operation": {"effect": "note"}}))
    store.submit_observation(dsn, _cmd({"attempt_id": "w1",
                                        "content": {"text": "<script>evil()</script>"}}))
    app = api.create_app(dsn, gateway=None, token="test-token")
    return TestClient(app, headers={"x-operator-token": "test-token"})


def _events(dsn) -> int:
    return len(store.read_events(dsn)["events"])


def test_overview_renders_from_durable_records_with_gateway_down(client, migrated_db):
    body = client.get("/").text
    assert "models unavailable" in body
    assert "obligations: 1" in body
    assert "w1" in body and "op1" in body
    assert "a1" not in body or "capacity" in body


def test_investigation_view_escapes_generated_content(client):
    body = client.get("/investigations/i1").text
    assert "<svg" in body and "&lt;script&gt;" in body
    assert "<script>alert" not in body and "<script>evil" not in body
    assert "w1" in body and "op1" in body


def test_evidence_view_reads_durable_records(client):
    body = client.get("/evidence").text
    assert "&lt;script&gt;" in body or "observations" in body
    assert "<script>evil" not in body


def test_trial_views_show_pending_state_without_t5_tables(client, monkeypatch):
    from settlement import api as _api

    monkeypatch.setattr(_api, "t5_state", lambda dsn: {"installed": False, "tables": []})
    for path in ("/trials", "/learning", "/capabilities"):
        body = client.get(path).text
        assert "pending" in body
        assert "<script>alert" not in body


def test_gets_never_mutate_domain_state(client, migrated_db):
    before = _events(migrated_db)
    for path in ("/", "/investigations/i1", "/evidence", "/capabilities",
                 "/trials", "/learning", "/operations/op1"):
        assert client.get(path).status_code == 200
    assert _events(migrated_db) == before


def test_operator_auth_is_required(migrated_db):
    app = api.create_app(migrated_db, gateway=None, token="test-token")
    assert TestClient(app).get("/").status_code == 401
