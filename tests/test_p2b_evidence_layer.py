from __future__ import annotations

import uuid

from settlement import api, evidence, store
from settlement.common import Command


def _cmd(payload: dict) -> Command:
    return Command(request_id=f"p2b_{uuid.uuid4().hex[:12]}", payload=payload)


def _seed(dsn: str) -> None:
    store.seed_allocation(dsn, _cmd({"allocation_id": "a1", "domain": "cpu", "authorized": 100}))
    store.admit_commitment(dsn, _cmd({"investigation_id": "i1", "objective": "p2b layer probe"}))
    store.acquire_work(dsn, _cmd({"attempt_id": "w1", "investigation_id": "i1",
                                  "allocation_id": "a1"}))


def test_submit_observation_stays_in_attempt_layer(migrated_db):
    dsn = migrated_db
    _seed(dsn)
    store.submit_observation(dsn, _cmd({"attempt_id": "w1", "content": {"note": "raw work note"}}))
    inv = api.investigation_data(dsn, "i1")
    assert any("raw work note" in str(o["content"]) for o in inv["observations"])
    assert api.evidence_data(dsn)["observations"] == []


def test_register_observation_mirrors_into_both_layers(migrated_db):
    dsn = migrated_db
    _seed(dsn)
    evidence.register_observation(dsn, _cmd({}), "w1", {"text": "sensor reading"},
                                  source_identity="sensor-1")
    assert any(o["attempt_id"] == "w1" for o in api.evidence_data(dsn)["observations"])
    inv = api.investigation_data(dsn, "i1")
    assert any("sensor reading" in str(o["content"]) for o in inv["observations"])
