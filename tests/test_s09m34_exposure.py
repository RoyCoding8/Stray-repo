"""S09-M34 exposure retirement gate."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

DB = "s09_m34_exposure"
DSN = "dbname=%s host=/var/run/postgresql user=ubuntu" % DB
MIGRATIONS = ROOT / "migrations"


@pytest.fixture(scope="module")
def store():
    assert "live" not in DSN
    assert DB.startswith("s09_m34_")
    subprocess.run(["createdb", "-h", "/var/run/postgresql",
                    "-U", "ubuntu", DB],
                   check=True, capture_output=True, text=True, timeout=60)
    try:
        from settlement import db
        db.apply_migrations(DSN, MIGRATIONS)
        yield DSN
    finally:
        subprocess.run(["dropdb", "-h", "/var/run/postgresql",
                        "-U", "ubuntu", DB],
                       capture_output=True, text=True, timeout=60)


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
