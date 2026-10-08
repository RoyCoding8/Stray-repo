from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from settlement import api, store
from rsi import genome
from settlement.common import Command, ResultCode


def test_operator_auth_is_required(migrated_db):
    app = api.create_app(migrated_db, gateway=None, token="test-token")
    assert TestClient(app).get("/").status_code == 401


def test_rsi_views_render_committed_lineage_with_gateway_down(migrated_db, tmp_path):
    seed = genome.Genome({"AGENTS.md": b"<script>inert</script>"})
    genome.publish(migrated_db, seed, staging_root=tmp_path / "stage",
                   artifacts_root=tmp_path / "art", parent=None, origin="test")
    client = TestClient(api.create_app(migrated_db, token="test-token"),
                        headers={"x-operator-token": "test-token"})
    page = client.get("/genomes")
    assert page.status_code == 200
    assert seed.digest in page.text
    assert "models unavailable" in page.text
    assert client.get("/episodes").status_code == 200
    assert client.get("/learning").status_code == 404
