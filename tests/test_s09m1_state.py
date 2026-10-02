"""S09-M1 state: migration 0017, selection extraction, fence, legacy drain."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from test_s09_migrate_callers import admit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01.s09_run_isolation import create_disposable_db, \
    disposable_db, drop_disposable_db

RUN_TOKEN = "m1state"
MIGRATIONS = ROOT / "migrations"

CHARTER = {"objective": "smaller valid explanatory examples",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 6, "diagnostic_queries": 16}
TASK = "ad01-w0-dev-sw-00"


@pytest.fixture(scope="module")
def store():
    database = create_disposable_db(RUN_TOKEN, migrations_dir=MIGRATIONS)
    try:
        yield database.dsn
    finally:
        drop_disposable_db(database)


def _pinned_trajectory():
    """`trajectory` pinned to the un-namespaced campaign id form.

    `NAMESPACE_TOKEN` is process-global and nothing ever clears it, so any
    earlier campaign test that calls `scripts.s09_pilot.run_study` leaves its
    own token behind for the rest of the pytest session. Unpinned, `campaign_id`
    then mints `ad01-w0-I-51-pe`, which `resume_campaign` refuses as malformed.
    The empty token is the only form it accepts.
    """
    from experiments.ad01 import trajectory
    trajectory.set_namespace_token("")
    return trajectory


def test_0017_creates_policy_and_exposure_tables(store):
    trajectory = _pinned_trajectory()
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
    from experiments.ad01 import selection
    trajectory = _pinned_trajectory()
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
        allocation_id=allocation, policy=admit("old"))
    assert resolved["requested"] == "old"
    assert resolved["selected"] == "old"
    assert resolved["executed"] == "incumbent"
    assert "member execution failed" in resolved["fallback_reason"]
    [empty] = trajectory.run_use(
        {"campaign_id": cid, "members": [], "queries": 0},
        0, "I", [TASK], {}, dsn=store,
        allocation_id=allocation, policy=admit("old"))
    assert empty["status"] == "refused"
    assert empty["selected"] == "refused"
    assert empty["executed"] == "refused"
    assert empty["output"] == {}
    assert "absent from the repertoire" in empty["fallback_reason"]
    [refused] = trajectory.run_use(
        repertoire, 0, "I", [TASK], {}, dsn=store,
        allocation_id=allocation, policy=admit("old"),
        release_id="s09-m1-never-bound")
    assert refused["status"] == "refused"
    assert refused["selected"] == "refused"
    assert refused["executed"] == "refused"
    assert refused["output"] == {}
    assert "s09-m1-never-bound" in refused["fallback_reason"]


def test_consolidated_path_carries_protected_target_fence(store):
    from experiments.ad01 import worlds
    trajectory = _pinned_trajectory()
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
    trajectory = _pinned_trajectory()
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


def test_a_foreign_namespace_token_cannot_derail_this_file():
    """The reason this file pins its namespace, asserted on its own.

    `NAMESPACE_TOKEN` is process-global and nothing clears it, so the whole
    suite runs in a process whose token depends on which file imported first.
    A foreign token has to leave this file's campaign id resumable.
    """
    from experiments.ad01 import trajectory
    trajectory.set_namespace_token("a-token-another-test-left-behind")
    try:
        cid = _pinned_trajectory().campaign_id(0, "I", 51)
        assert cid == "ad01-w0-I-51", (
            "a foreign namespace token leaked into this file's campaign id")
        parts = cid.split("-")
        assert len(parts) == 4 and parts[0] == "ad01" and parts[2] in ("I", "R")
    finally:
        trajectory.set_namespace_token("")


def test_the_store_is_one_this_run_created(store):
    """A dropped store must never be a store somebody else still runs on.

    A fixed database name is shared state: any other suite that creates the
    same name destroys this run's rows, and the failures read as product
    defects rather than as the collision they are. The name carries a
    per-run token, so only this run's name is ever destroyed.
    """
    name = store.split("dbname=")[1].split()[0]

    assert name.startswith("s09iso_m1state_"), name


def test_the_store_survives_a_second_module_scope():
    """Re-deriving the store must not reuse this module's database.

    The collision that produced the original failures was two runs of this
    file at once. Each run's fixture mints its own name, so a second fixture
    can never observe or destroy the first one's database.
    """
    with disposable_db(RUN_TOKEN) as other:
        assert other.name.startswith("s09iso_m1state_"), other.name
