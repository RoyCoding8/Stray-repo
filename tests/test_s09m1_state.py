"""S09-M1 state: migration 0017, selection extraction, fence, legacy drain."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

DB = "s09_m1_state"
DSN = "dbname=%s host=/var/run/postgresql user=ubuntu" % DB
MIGRATIONS = ROOT / "migrations"

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 6, "diagnostic_queries": 16}
TASK = "ad01-w0-dev-sw-00"


@pytest.fixture(scope="module")
def store():
    assert "live" not in DSN
    assert DB.startswith("s09_m1_")
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


def test_0017_creates_policy_and_exposure_tables(store):
    from experiments.ad01 import trajectory
    with trajectory._read_conn(store) as conn:
        names = conn.execute(
            "SELECT name FROM schema_migrations WHERE name = %s",
            ("0017_s09_state.sql",)).fetchone()
        assert names is not None
        policy = conn.execute(
            "SELECT column_name, data_type FROM information_schema.columns"
            " WHERE table_name = 's09_policy_state'"
            " ORDER BY column_name").fetchall()
        exposure = conn.execute(
            "SELECT column_name, data_type FROM information_schema.columns"
            " WHERE table_name = 's09_assessment_exposure'"
            " ORDER BY column_name").fetchall()
    assert [r["column_name"] for r in policy] == [
        "accepted_action", "attempt_id", "created_at", "driver_version",
        "effect_id", "effect_record", "investigation_id",
        "policy_input", "policy_output", "provenance", "seq",
        "state_transition", "status", "updated_at"]
    assert [r["column_name"] for r in exposure] == [
        "batch_id", "exposed_to", "recorded_at", "retired_at"]
    import scripts.checkpoint as checkpoint
    state = checkpoint._db_state(store)
    assert "0017_s09_state.sql" in state["migrations"]
    assert state["row_counts"]["s09_policy_state"] == 0
    assert state["row_counts"]["s09_assessment_exposure"] == 0


def test_public_use_resolves_repertoire_scoped_selection(store):
    from experiments.ad01 import selection, trajectory
    assert trajectory._select_member is selection.select_member
    members = [{"capability_id": name, "scope": {"family": "software"}}
               for name in ("old", "revision")]
    task = {"family": "software"}
    assert selection.select_member(
        {"members": members}, task) == members[0]
    assert selection.select_member(
        {"members": members[::-1]}, task) == members[::-1][0]
    assert selection.select_member(
        {"members": members}, {"family": "graph"}) is None
    assert selection.select_member(
        {"members": members}, task, dsn=store) == members[0]
    assert selection.active_binding_for(store, "software") is None
    cid = trajectory.campaign_id(0, "I", 52)
    allocation = trajectory.authorize_campaign(
        store, cid, authorized=1000)["allocation_id"]
    repertoire = {"campaign_id": cid, "members": members}
    [resolved] = trajectory.run_use(
        repertoire, 0, "I", [TASK], {}, dsn=store,
        allocation_id=allocation)
    assert resolved["requested"] == "old"
    assert resolved["selected"] == "old"
    assert resolved["executed"] == "incumbent"
    assert "member execution failed" in resolved["fallback_reason"]
    [empty] = trajectory.run_use(
        {"campaign_id": cid, "members": [], "queries": 0},
        0, "I", [TASK], {}, dsn=store,
        allocation_id=allocation)
    assert empty["selected"] == "incumbent"
    assert empty["executed"] == "incumbent"
    [refused] = trajectory.run_use(
        repertoire, 0, "I", [TASK], {}, dsn=store,
        allocation_id=allocation, release_id="s09-m1-never-bound")
    assert refused["selected"] == "incumbent"
    assert refused["executed"] == "incumbent"
    assert "s09-m1-never-bound" in refused["fallback_reason"]


def test_consolidated_path_carries_protected_target_fence(store):
    from experiments.ad01 import trajectory, worlds
    target = next(p.stem for p in sorted(
        worlds.FROZEN_DIR.rglob("*.json")) if "w0-transfer-sw" in p.stem)
    proposal = {"unknown": "Does this preserve the witness?",
                "basis_references": [],
                "next_action": {"kind": "diagnostic", "diagnostic": "software",
                                "task_id": target},
                "requested_resources": {"queries": 1}}
    admitted = trajectory.admit_investigation(
        proposal, {"observations": []}, CHARTER,
        {"world": 0, "arm": "I", "seq": 0})
    assert admitted["decision"] == "admitted"
    cid = trajectory.campaign_id(0, "I", 50)
    trajectory.authorize_campaign(store, cid, authorized=1000)
    trajectory.ensure_campaign(store, cid, 0, "I", CHARTER, CAPS,
                               tasks=[TASK])
    trajectory.accept_action(store, cid, 0, proposal)
    observation, episode, spend, _decision = trajectory.execute_pending(
        store, cid, 0, task_id=TASK, capability_id="seed-sw-greedy",
        caps=CAPS,
        seed_obs={"observation_id": "obs-x", "task_id": TASK,
                  "capability_id": "seed-sw-greedy",
                  "verdict": "unmeasured"},
        charter=CHARTER, boundary={"world": 0, "arm": "I", "seq": 0},
        experience={"observations": []},
        state={"dev_episodes": 0, "model_calls": 0,
               "construction_calls": 0},
        study_root=cid)
    assert episode["disposition"] == "no-candidate"
    assert "protected-use target" in episode["fallback_reason"]
    assert spend == 0
    assert observation["verdict"] == "unmeasured"
    settled, _pending = trajectory._read_campaign(store, cid)
    assert settled == {}


def test_legacy_pending_drains_without_relabel(store):
    from experiments.ad01 import trajectory
    cid = trajectory.campaign_id(0, "I", 51)
    trajectory.authorize_campaign(store, cid, authorized=1000)
    first = trajectory.run_campaign(
        0, "I", CHARTER, dict(CAPS, max_boundaries=1),
        tasks=[TASK, "ad01-w0-dev-sw-01"], campaign_seq=51, dsn=store)
    assert [b["seq"] for b in first["boundaries"]] == [0]
    legacy = {"basis_references": [], "unknown": "u", "question": "q1",
              "next_action": {"kind": "diagnostic",
                              "diagnostic": "diagnostic_resolves",
                              "task_id": "ad01-w0-dev-sw-01"}}
    trajectory.record_decision(store, cid, 1, legacy)
    resumed = trajectory.resume_campaign(store, cid, CHARTER, CAPS)
    assert [b["seq"] for b in resumed["boundaries"]] == [0, 1]
    assert resumed["boundaries"][0]["observation_id"] == \
        first["boundaries"][0]["observation_id"]
    assert resumed["boundaries"][1]["decision"] == legacy
    with trajectory._read_conn(store) as conn:
        rows = conn.execute(
            "SELECT seq, provenance, status FROM s09_policy_state"
            " WHERE investigation_id = %s ORDER BY seq",
            (cid,)).fetchall()
    assert [(r["seq"], r["provenance"], r["status"]) for r in rows] == [
        (0, "s09-m1", "incorporated"), (1, "legacy-drain", "incorporated")]
