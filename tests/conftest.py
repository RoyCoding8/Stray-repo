from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

from settlement import db


def _dsn() -> str:
    dsn = os.environ.get("SETTLEMENT_TEST_DSN", "")
    if not dsn:
        pytest.skip("SETTLEMENT_TEST_DSN is not configured")
    return dsn


@pytest.fixture()
def dsn():
    return _dsn()


@pytest.fixture()
def migrated_db(dsn):
    db.apply_migrations(dsn, Path(__file__).parent.parent / "migrations")
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            for table in _tables(cur):
                cur.execute(f'TRUNCATE TABLE "{table}" CASCADE')
        conn.commit()
    yield dsn


def _tables(cur) -> list[str]:
    cur.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename != 'schema_migrations'"
    )
    return [row[0] for row in cur.fetchall()]


@pytest.fixture()
def tmp_roots(tmp_path):
    artifacts = tmp_path / "artifacts"
    staging = tmp_path / "staging"
    artifacts.mkdir()
    staging.mkdir()
    return {"artifacts": artifacts, "staging": staging}


def unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"
