"""A49: a campaign that dies in a boundary leaves no orphan.

The `hashlib` NameError at `_method_panel` is the instance; the invariant is
the point. A boundary that raises between admission and release used to leave
an operation held on the mission entry, and this file pins two facts about
that state:

- a boundary which crashes never mints a release, so a campaign that cannot
  assess its method cannot claim one (non-vacuity, negative direction);
- a rerun of the SAME campaign id drains the held entry and reaches the same
  end state a clean run reaches (non-vacuity, positive direction).

Both run the real public entry through the offline fixture gateway.
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_inv_a_chain as chain
import test_inv_a_reviewer_source as reviewer

MIGRATIONS = ROOT / "migrations"

CRASH = "injected-boundary-crash"


@pytest.fixture(scope="module")
def store():
    from experiments.ad01 import s09_run_isolation as iso

    database = iso.create_disposable_db("a49crash",
                                        admin_dsn=os.environ.get(
                                            "SETTLEMENT_TEST_DSN") or None,
                                        migrations_dir=MIGRATIONS)
    try:
        yield database.dsn
    finally:
        iso.drop_disposable_db(database)


class _BoundaryCrash(Exception):
    pass


def _campaign(store, seq):
    from experiments.ad01 import trajectory

    cid = trajectory.campaign_id(0, "I", seq)
    gateway = chain.Constructor()
    return cid, gateway, trajectory.run_campaign(
        0, "I", chain.CHARTER, chain.CAPS, tasks=list(chain.ACQUIRE_TASKS),
        campaign_seq=seq, dsn=store,
        consumer=chain._consumer(store, cid, reviewer.CHAIN_SOURCE,
                                 gateway=gateway),
        constructor="model", gateway=gateway, model="a5-reviewer-double")


def _held(store, cid):
    from experiments.ad01 import mission

    return mission.read_in_flight(store, cid)


def _releases(store):
    from experiments.ad01 import trajectory

    with trajectory._read_conn(store) as conn:
        rows = conn.execute("SELECT id FROM capability_releases").fetchall()
        conn.commit()
    return sorted(dict(r)["id"] for r in rows)


def _crash_in_panel(monkeypatch):
    """Raise where the NameError raised, without touching the function."""
    from experiments.ad01 import trajectory

    def boom(*args, **kwargs):
        raise _BoundaryCrash(CRASH)

    monkeypatch.setattr(trajectory, "_method_panel", boom)


def test_a_crashed_boundary_mints_no_release_and_holds_its_operation(
        store, monkeypatch):
    """The crash is loud, and it leaves exactly one owed operation.

    Non-vacuity, negative direction. The panel raised, so no assessment ran
    and no `capability_releases` row may exist for this campaign. The
    admitted operation is still held, which is what makes the next test's
    drain meaningful rather than vacuous.
    """
    seq = 401
    cid = trajectory_id(store, seq)
    _crash_in_panel(monkeypatch)
    with pytest.raises(_BoundaryCrash):
        _campaign(store, seq)

    assert _releases(store) == [], (
        "a boundary that never reached its assessment minted a release")
    held = _held(store, cid)
    assert [(item.seq, item.status) for item in held] == [(1, "held")], held


def test_the_rerun_drains_the_held_operation_and_reaches_the_clean_state(
        store, monkeypatch):
    """The held operation has an owner, and it is the rerun.

    Non-vacuity, positive direction. The first run above crashed holding
    seq 1. This run starts from that state and must end where a run that
    never crashed ends: nothing held, every row incorporated, and the same
    release bound. So the rerun's pass is a consequence of correct code, not
    an artefact of the crash having skipped the branch.
    """
    seq = 401
    cid = trajectory_id(store, seq)
    before = _releases(store)
    assert _held(store, cid), "precondition: an operation is still held"

    monkeypatch.undo()
    _, _, out = _campaign(store, seq)

    assert [item.as_json() for item in _held(store, cid)] == [], (
        "the rerun completed but left an operation held")
    with _conn(store) as conn:
        rows = conn.execute(
            "SELECT seq, status FROM s09_policy_state"
            " WHERE investigation_id = %s ORDER BY seq", (cid,)).fetchall()
    assert [(r["seq"], r["status"]) for r in rows] == [
        (0, "incorporated"), (1, "incorporated"), (2, "incorporated")]

    bound = _releases(store)
    assert len(bound) > len(before), (
        "the drained rerun bound nothing, so the release is not proven")
    assert [e.get("method_release_id") for e in out["episodes"]
            if e.get("method_release_id")] == bound[-1:]
    assert out["episodes"][1]["disposition"] == "retained"


def test_the_release_names_the_bytes_the_campaign_retained(store, monkeypatch):
    """The drained release is the method's, not the policy's.

    A drain that produced some release would satisfy the count above. This
    pins which one: the digest is the retained member's own bytes and
    differs from the use policy's.
    """
    from experiments.ad01 import trajectory

    cid = trajectory_id(store, 401)
    with _conn(store) as conn:
        row = conn.execute(
            "SELECT effect_record FROM s09_policy_state"
            " WHERE investigation_id = %s AND seq = 1", (cid,)).fetchone()
        release = conn.execute(
            "SELECT id, versions, invalidation FROM capability_releases"
            " ORDER BY id").fetchall()
    episode = dict(dict(row["effect_record"])["episode"])
    member = episode["executable"]
    assert member["source_digest"] == hashlib.sha256(
        member["method_source"].encode("utf-8")).hexdigest()

    (only,) = release
    assert only["id"] == trajectory.method_release_id(
        cid, member["source_digest"])
    assert list(only["versions"]) == [member["capability_id"]]
    assert only["invalidation"]["candidate_digest"] == member["source_digest"]
    assert member["source_digest"] != reviewer.digest(
        reviewer.use_source(member["capability_id"]))


def trajectory_id(store, seq):
    from experiments.ad01 import trajectory

    return trajectory.campaign_id(0, "I", seq)


def _conn(store):
    from experiments.ad01 import trajectory

    return trajectory._read_conn(store)


def test_a_second_campaign_id_on_a_clean_store_binds_its_own_release(store):
    """A disjoint campaign on the same store binds its own release.

    The poisoning claim was that a second campaign id skips the broken branch
    and passes for that reason. This is the control: a campaign on a store
    that was never crashed must bind a release naming its OWN campaign id,
    not the first one's, so a pass there is a fact about the code rather than
    about a crash it avoided.
    """
    seq = 402
    cid = trajectory_id(store, seq)
    before = set(_releases(store))
    _, _, out = _campaign(store, seq)

    bound = set(_releases(store)) - before
    assert [i for i in bound if i.startswith("ad01-%s-method-" % cid)], (
        "the second campaign bound no release of its own: %s" % sorted(bound))
    assert out["episodes"][1]["disposition"] == "retained"
    assert [item.as_json() for item in _held(store, cid)] == []