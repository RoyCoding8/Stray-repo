"""Releasing a settled operation must not drop another writer's entry.

`mission.py` owns `investigations.in_flight`. Three of its four writers read
under `FOR UPDATE` and rewrite the column in the same transaction:
`admit_operation` (line 422), `resume_operation` (line 507), and, since
pass 1, `run._hold_on_mission_entry` (line 617). `_replace` (line 449) is the
fourth writer and takes no lock at all, on a *separate connection* from the
`read_in_flight` that computed its argument.

`release_operation` calls `read_in_flight`, filters one attempt out in Python,
then hands the whole list to `_replace`, which overwrites the column with a
list built from a read that can be arbitrarily stale. Two writers on the same
column, one of them unlocked, is the asymmetry that let pass 1's defect
survive in the first place.

The live caller is `trajectory._s09_mark_incorporated` (line 331), which runs
per incorporated boundary. Two boundaries of one campaign settling at the same
moment each read the pre-settle list and each write back only its own removal,
so the other boundary's settled operation stays on the entry. A later
`resume_operation` then restores work that already ran, which is exactly the
double-counted effect that module's own docstring says it exists to prevent.

The race is a property of the transaction, so this drives real PostgreSQL with
real concurrency rather than mocking a scheduler.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

MIGRATIONS = ROOT / "migrations"
RUN_TOKEN = "p2missionrelease"

CHARTER = {"objective": "release two settled operations without losing either",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 3, "diagnostic_queries": 16, "model_calls": 20}
DEV_TASK = "ad01-w0-dev-sw-00"
PROGRAM_DIGEST = "21bc17cde3811fd4d3fa0289278f63c3afe0108f0ef4438915040219cf390093"


@pytest.fixture(scope="module")
def store():
    from experiments.ad01 import s09_run_isolation as iso

    admin_dsn = os.environ.get("SETTLEMENT_TEST_DSN") or None
    database = iso.create_disposable_db(RUN_TOKEN, admin_dsn=admin_dsn,
                                        migrations_dir=MIGRATIONS)
    try:
        yield database.dsn
    finally:
        iso.drop_disposable_db(database, admin_dsn=admin_dsn)


def _decision(question: str) -> dict:
    return {"basis_references": [],
            "question": question,
            "next_action": {"kind": "diagnostic", "task_id": DEV_TASK,
                            "diagnostic": "software",
                            "capability_id": "seed-sw-greedy"}}


def _three_held_attempts(store) -> tuple:
    """One investigation holding three admitted operations on three attempts.

    Admitted through the owning seam, so the in-flight rows are the shape the
    mission module itself writes rather than a hand-built fixture.
    """
    from experiments.ad01 import mission, trajectory

    trajectory.set_namespace_token("")
    cid = trajectory.campaign_id(0, "I", 83)
    trajectory.authorize_campaign(store, cid, authorized=100000)
    made = trajectory.ensure_campaign(store, cid, 0, "I", CHARTER, CAPS,
                                      tasks=[DEV_TASK])
    assert made["admitted"] is True, "the campaign admitted nothing"
    admitted = [trajectory.accept_action(store, cid, seq, _decision(f"p2 boundary {seq}"),
                                         program_digest=PROGRAM_DIGEST)
                for seq in (0, 1, 2)]
    assert len(set(admitted)) == 3, f"the admissions collided on one attempt: {admitted}"
    held = mission.read_in_flight(store, cid)
    assert len(held) == 3, f"expected three held operations, got {held}"
    return cid, admitted


def test_two_concurrent_releases_keep_each_others_operations(store):
    """Neither release drops the other writer's operation.

    Two boundaries of one campaign settle at the same moment. The assertion is
    literal: after both settle, the entry holds exactly the third operation
    they did not touch. An unlocked `_replace` leaves the loser's operation
    behind, so a later `resume_operation` restores an effect that already ran.
    """
    from experiments.ad01 import mission

    cid, (first, second, third) = _three_held_attempts(store)

    gate = threading.Barrier(2, timeout=60)
    errors: list = []

    def settle(attempt_id: str) -> None:
        try:
            gate.wait()
            mission.release_operation(store, cid, attempt_id)
        except Exception as exc:  # noqa: BLE001 - collected and asserted below
            errors.append((attempt_id, type(exc).__name__, str(exc)))

    threads = [threading.Thread(target=settle, args=(first,)),
               threading.Thread(target=settle, args=(second,))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    assert not any(thread.is_alive() for thread in threads), (
        "a release thread never finished, so the race was not exercised")

    assert errors == [], f"a release raised rather than racing cleanly: {errors}"

    remaining = mission.read_in_flight(store, cid)
    assert [item.attempt_id for item in remaining] == [third], (
        "a concurrent release dropped another writer's operation; the entry "
        f"reads back {[item.attempt_id for item in remaining]}, and a later "
        "resume would restore an effect that already ran")