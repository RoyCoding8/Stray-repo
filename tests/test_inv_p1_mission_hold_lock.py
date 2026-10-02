"""Two concurrent barriers must not lose one another's hold.

Lane C6 added `run._hold_on_mission_entry`, a read-modify-write over the
`investigations.in_flight` column. The module that owns that column,
`experiments/ad01/mission.py`, takes `FOR UPDATE` before it reads, in both
`admit_operation` and `resume_operation`. The new code reads and writes in
two separate connections with no lock, so two barriers that suspend two
different attempts of the same investigation at the same time each read the
pre-barrier list and each write back only its own edit. The second write
silently drops the first barrier's `status="suspended"` and `barrier_ref`,
and the attempt it named reads back as still held.

That is the lost update lane A4b repaired on the other side of this batch,
reproduced in the function that batch's own successor wrote. The C6
docstring says the record happens first "so the record exists if the write
is refused", but a lost write does not leave a record that is merely
unrefused. It leaves a record that reads as never marked.

The race is a property of the transaction, so this drives real PostgreSQL
with real concurrency rather than mocking a scheduler.
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
RUN_TOKEN = "p1missionhold"

CHARTER = {"objective": "hold two pending operations across a restart",
           "freeze_id": "ad01"}
CAPS = {"max_boundaries": 2, "diagnostic_queries": 16, "model_calls": 20}
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


def _two_held_attempts(store) -> tuple:
    """One investigation holding two admitted operations on two attempts.

    Admitted through the owning seams, so the in-flight rows are the shape
    the mission module itself writes rather than a hand-built fixture.
    """
    from experiments.ad01 import mission, trajectory

    trajectory.set_namespace_token("")
    cid = trajectory.campaign_id(0, "I", 71)
    trajectory.authorize_campaign(store, cid, authorized=100000)
    made = trajectory.ensure_campaign(store, cid, 0, "I", CHARTER, CAPS,
                                      tasks=[DEV_TASK])
    assert made["admitted"] is True, "the campaign admitted nothing"
    first = trajectory.accept_action(store, cid, 0, _decision("p1 first boundary"),
                                     program_digest=PROGRAM_DIGEST)
    second = trajectory.accept_action(store, cid, 1, _decision("p1 second boundary"),
                                      program_digest=PROGRAM_DIGEST)
    assert first != second, "both admissions landed on one attempt"
    held = mission.read_in_flight(store, cid)
    assert len(held) == 2, f"expected two held operations, got {held}"
    assert {item.attempt_id for item in held} == {first, second}, held
    return cid, first, second


def test_two_concurrent_barriers_both_leave_their_hold(store):
    """Both holds survive two barriers racing on one mission entry.

    Each barrier suspends a different attempt of the same investigation. The
    assertion is literal: each attempt reads back as `suspended` and each
    carries the barrier_ref it was suspended under. A lost update leaves one
    of the two reading `held` with an empty barrier_ref.
    """
    from settlement import run as settlement_run

    cid, first, second = _two_held_attempts(store)

    gate = threading.Barrier(2, timeout=60)
    errors: list = []

    def suspend(attempt_id: str, barrier_ref: str) -> None:
        try:
            gate.wait()
            settlement_run.suspend_for_barrier(store, attempt_id, barrier_ref)
        except Exception as exc:  # noqa: BLE001 - collected and asserted below
            errors.append((barrier_ref, type(exc).__name__, str(exc)))

    threads = [
        threading.Thread(target=suspend, args=(first, "p1-barrier-one")),
        threading.Thread(target=suspend, args=(second, "p1-barrier-two")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    assert not any(thread.is_alive() for thread in threads), (
        "a barrier thread never finished, so the race was not exercised")

    assert errors == [], f"a barrier raised rather than racing cleanly: {errors}"

    from experiments.ad01 import mission

    held = {item.attempt_id: item for item in mission.read_in_flight(store, cid)}
    assert held[first].status == "suspended", (
        f"the first barrier's hold was lost, {first} reads back "
        f"{held[first].status!r} with barrier_ref "
        f"{held[first].barrier_ref!r}")
    assert held[first].barrier_ref == "p1-barrier-one", held[first]
    assert held[second].status == "suspended", (
        f"the second barrier's hold was lost, {second} reads back "
        f"{held[second].status!r} with barrier_ref "
        f"{held[second].barrier_ref!r}")
    assert held[second].barrier_ref == "p1-barrier-two", held[second]
