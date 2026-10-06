"""S09-M34 exposure retirement gate."""

from __future__ import annotations

import os
import re
import sys
import uuid
from pathlib import Path

import pytest

from experiments.ad01.s09_run_isolation import DB_PREFIX, \
    create_disposable_db, disposable_db, drop_disposable_db

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

MIGRATIONS = ROOT / "migrations"
LOCAL_HOST = "/var/run/postgresql"
LOCAL_DSN = "dbname=postgres host=%s user=ubuntu" % LOCAL_HOST

RUN_TOKEN = "m34exp%s" % uuid.uuid4().hex[:10]


def _dbname(dsn: str) -> str:
    return dict(field.split("=", 1) for field in dsn.split()
                if "=" in field).get("dbname", "").strip("'\"")


def _admin_dsn() -> str:
    """The DSN names the instance to create on, never a store to empty."""
    return _route()


@pytest.fixture(scope="module")
def store():
    admin = _admin_dsn()
    assert "live" not in _dbname(admin)
    database = create_disposable_db(RUN_TOKEN, admin_dsn=admin,
                                    migrations_dir=MIGRATIONS)
    try:
        yield database.dsn
    finally:
        drop_disposable_db(database, admin_dsn=admin)


def test_the_store_is_named_for_this_run_not_for_the_file(store):
    """Two concurrent runs of this module must not share a store.

    Exposure retirement reads a live store. The fixture used to create and
    drop one fixed name, so a sibling's teardown destroyed this run's store
    mid-module and the failures read as product defects rather than as the
    collision they are. Only the per-run suffix keeps the two disjoint, so
    that is what this pins.
    """
    mine = _dbname(store)

    assert mine.startswith(DB_PREFIX + "_" + RUN_TOKEN), mine

    with disposable_db(RUN_TOKEN, admin_dsn=_admin_dsn()) as fresh:
        assert fresh.name != mine
        assert fresh.name.startswith(DB_PREFIX + "_" + RUN_TOKEN)
        assert re.fullmatch(r"[0-9a-f]{12}", fresh.name.rsplit("_", 1)[1])
    assert mine != _dbname(LOCAL_DSN), mine


def test_exposure_retires_batch_for_descendants(store):
    from experiments.ad01 import learner
    batch = "batch-exposure-1"
    assert learner.is_retired(store, batch) is False
    learner.record_exposure(store, batch, "consumer-a")
    assert learner.is_retired(store, batch) is True
    with pytest.raises(learner.LearnerRefused, match="retired"):
        learner.require_unretired(store, batch, "descendant-b")


def test_constructor_prompt_carries_no_sealed_bytes(store):
    from experiments.ad01 import learner
    _ = store
    sealed = {"observation_id": "obs-sealed-x",
              "task_id": "ad01-w0-dev-sw-00",
              "capability_id": "seed-sw-greedy",
              "verdict": "preserved",
              "access_label": "hidden",
              "hidden_answer": "sealed-bytes-abc"}
    prompt = learner.visible_prompt(
        {"objective": "x", "freeze_id": "ad01"},
        ["ad01-w0-dev-sw-00"],
        {"observations": [sealed]}, [], {"queries": 16}, None)
    assert "sealed-bytes-abc" not in prompt
    assert "obs-sealed-x" not in prompt
