"""A new SQL mission must have the charter its public declaration needs."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import mission
from experiments.ad01.s09_run_isolation import create_disposable_db, \
    drop_disposable_db

MIGRATIONS = ROOT / "migrations"
RUN_TOKEN = "mjr-charter"


@pytest.fixture(scope="module")
def store():
    admin_dsn = os.environ.get("SETTLEMENT_TEST_DSN") or None
    database = create_disposable_db(RUN_TOKEN, admin_dsn=admin_dsn,
                                    migrations_dir=MIGRATIONS)
    try:
        yield database.dsn
    finally:
        drop_disposable_db(database, admin_dsn=admin_dsn)


def test_initial_mission_rejects_missing_charter(store):
    with pytest.raises(mission.MissionRefused, match="initial mission"):
        mission.record_mission(
            store, "mjr-missing-charter", frontier={"open": ["x"]})

    with mission.connect(store) as conn:
        row = conn.execute(
            "SELECT count(*) AS n FROM investigations"
            " WHERE id = %s", ("mjr-missing-charter",)).fetchone()
        conn.commit()
    assert int(row["n"]) == 0
