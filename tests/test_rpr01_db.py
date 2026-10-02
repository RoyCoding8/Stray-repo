"""RPR-01 lane database: real PostgreSQL 16 sentinel for settlement_cb01src."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from settlement import db
from settlement.common import payload_digest


def _lane_dsn(dsn: str) -> str:
    from conftest_isolation import dsn_with_dbname
    return dsn_with_dbname(dsn, "settlement_cb01src")


def test_lane_database_is_real_postgresql_16(dsn):
    import psycopg
    from psycopg import errors
    assert dsn.startswith("postgresql://")
    lane = _lane_dsn(dsn)
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            try:
                cur.execute('CREATE DATABASE "settlement_cb01src" OWNER ubuntu')
            except errors.DuplicateDatabase:
                pass
    with db.connect(lane) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version()")
            version = cur.fetchone()[0]
            assert "PostgreSQL 16" in version
            digest = payload_digest({"lane": "cb01-source"})
            cur.execute("CREATE TEMP TABLE rpr01_sentinel (digest TEXT)")
            cur.execute("INSERT INTO rpr01_sentinel (digest) VALUES (%s)",
                        (digest,))
            cur.execute("SELECT digest FROM rpr01_sentinel")
            assert cur.fetchone()[0] == digest
        conn.rollback()
