import os
import uuid

from fastapi.testclient import TestClient

from settlement import api, steward, store
from settlement.common import Command, ResultCode


def _cmd(payload):
    return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload)


def _client(dsn):
    return TestClient(api.create_app(dsn, gateway=None, token="review-token"))


def test_login_flow_sets_cookie_and_enables_commands(migrated_db):
    client = _client(migrated_db)
    assert client.get("/login").status_code == 200
    denied = client.post("/login", content="token=nope",
                         headers={"content-type": "application/x-www-form-urlencoded"})
    assert denied.status_code == 403
    signed = client.post("/login", content="token=review-token",
                         headers={"content-type": "application/x-www-form-urlencoded"})
    assert signed.status_code in (200, 303)
    assert client.cookies.get("operator_token") == "review-token"
    page = client.get("/")
    assert page.status_code == 200
    assert "models unavailable" in page.text


def test_browser_unauthenticated_get_points_to_login(migrated_db):
    bare = TestClient(api.create_app(migrated_db, gateway=None, token="review-token"))
    response = bare.get("/", headers={"accept": "text/html"})
    assert response.status_code == 401
    assert "/login" in response.text


def test_generated_token_is_unguessable_and_unique(monkeypatch):
    monkeypatch.delenv("OPERATOR_TOKEN", raising=False)
    first, second = api.operator_token(), api.operator_token()
    assert len(first) == 32 and len(second) == 32
    assert first != second
    assert api.operator_token(explicit="fixed") == "fixed"


def test_supervision_scope_refuses_task_atomically(migrated_db):
    dsn = migrated_db
    store.seed_allocation(dsn, _cmd({"allocation_id": "root", "domain": "agenda",
                                     "authorized": 100}))
    store.subdivide_allocation(dsn, _cmd({"parent_id": "root", "child_id": "sup",
                                          "authorized": 40, "owner_scope": "supervision"}))
    store.admit_commitment(dsn, _cmd({"investigation_id": "inv1", "objective": "o"}))
    refused = store.acquire_work(dsn, _cmd({"investigation_id": "inv1", "attempt_id": "a1",
                                            "allocation_id": "sup"}))
    assert refused.code == ResultCode.INSUFFICIENT_RESOURCES
    allowed = store.acquire_work(dsn, _cmd({"investigation_id": "inv1", "attempt_id": "a2",
                                            "allocation_id": "sup",
                                            "kind": "recovery"}))
    assert allowed.code == ResultCode.APPLIED
    assert steward.admit_task(
        dsn, _cmd({"investigation_id": "inv1", "attempt_id": "a3",
                   "allocation_id": "sup"})).code == ResultCode.INSUFFICIENT_RESOURCES


def test_quarantine_without_learning_slice_is_unavailable(migrated_db):
    out = steward.quarantine_subject(migrated_db, _cmd({"subject": "cap_x"}))
    assert out.code == ResultCode.UNAVAILABLE_DEPENDENCY
