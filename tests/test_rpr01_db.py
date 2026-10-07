"""RPR-01 verifies the suite's real PostgreSQL connection."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from settlement import db
from settlement.common import payload_digest


def test_lane_database_is_real_postgresql(dsn):
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_user, current_setting('server_version_num')")
            database, user, version_num = cur.fetchone()
            assert database and user
            assert int(version_num) >= 160000
            digest = payload_digest({"lane": "rpr01-temp-sentinel"})
            cur.execute("CREATE TEMP TABLE rpr01_sentinel (digest TEXT)")
            cur.execute("INSERT INTO rpr01_sentinel (digest) VALUES (%s)",
                        (digest,))
            cur.execute("SELECT digest FROM rpr01_sentinel")
            assert cur.fetchone()[0] == digest
        conn.rollback()
