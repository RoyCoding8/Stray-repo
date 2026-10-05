"""Two concurrent admissions must not lose one another's operation.

`experiments/ad01/mission.py` owns `investigations.in_flight`, and every
writer of that column reads the row under `FOR UPDATE` and rewrites it in the
same transaction. That discipline is what makes a second writer to this column
safe rather than a lost update, and this is the test that holds it.

The shape of the defect is not hypothetical in this repository. Lane P1 found
`run._hold_on_mission_entry` reading the column on one connection and writing
the whole list back from a second connection, so two barriers suspending two
attempts of one investigation each read the pre-barrier list and the second
write silently dropped the first barrier's entry. Lane P2 found the same thing
in `mission._replace`, which `release_operation` used to call across
connections. Both were repaired by moving the read and the write into one
locked transaction, and both repairs were pinned by racing two threads.

That path is gone now. What remains is the discipline itself, on the writer
that still holds the column, and nothing in the tree races it. This test is
that coverage: `admit_operation` is the writer whose transaction discipline
every other writer in the module is described against, so a refactor that
split its read from its write would restore, on the surviving writer, the
exact defect its two predecessors were deleted for.

The race is a property of the transaction, so this drives real PostgreSQL with
real concurrency rather than mocking a scheduler.
"""

from __future__ import annotations

import os
import sys
import threading
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

MIGRATIONS = ROOT / "migrations"
RUN_TOKEN = "p1missionadmit"

DECISION = {"basis_references": [],
            "question": "does the boundary express the decision",
            "next_action": {"kind": "diagnostic", "task_id": "dev-task-0",
                            "capability_id": "seed-sw-greedy"}}
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


@pytest.fixture()
def investigation(store) -> str:
    """One mission entry, its own row, so no run inherits another's admission."""
    from experiments.ad01 import mission

    investigation_id = "p1admit-%s" % uuid.uuid4().hex[:12]
    mission.record_mission(
        store, investigation_id,
        objective="admit two operations without losing either",
        environments=[{"instrument": "boolean-rule-v1", "split": "dev",
                       "seed": 4}])
    return investigation_id


def _admit(dsn: str, investigation_id: str, seq: int, attempt_id: str):
    from experiments.ad01 import mission

    return mission.admit_operation(
        dsn, investigation_id, seq=seq, attempt_id=attempt_id,
        decision=DECISION, program_digest=PROGRAM_DIGEST,
        task_id="dev-task-0", capability_id="seed-sw-greedy")


def test_two_concurrent_admissions_keep_each_others_operations(store,
                                                               investigation):
    """Neither admission drops the other writer's operation.

    Two boundaries of one investigation admit at the same moment. The
    assertion is literal: after both, the entry holds exactly the two
    operations they wrote, each under its own attempt id and program digest.
    A read and a write split across connections leaves the loser's operation
    absent, so a later resume restores nothing for a boundary that is owed a
    run.
    """
    from experiments.ad01 import mission

    assert mission.read_in_flight(store, investigation) == [], (
        "the mission entry started holding an operation this test did not "
        "admit")

    first = "p1-att-a"
    second = "p1-att-b"

    gate = threading.Barrier(2, timeout=60)
    errors: list = []

    def admit(seq: int, attempt_id: str) -> None:
        try:
            gate.wait()
            _admit(store, investigation, seq, attempt_id)
        except Exception as exc:  # noqa: BLE001 - collected and asserted below
            errors.append((attempt_id, type(exc).__name__, str(exc)))

    threads = [threading.Thread(target=admit, args=(0, first)),
               threading.Thread(target=admit, args=(1, second))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    assert not any(thread.is_alive() for thread in threads), (
        "an admission thread never finished, so the race was not exercised")

    assert errors == [], f"an admission raised rather than racing cleanly: {errors}"

    held = {item.attempt_id: item for item in mission.read_in_flight(store,
                                                                    investigation)}
    assert sorted(held) == [first, second], (
        "a concurrent admission dropped another writer's operation; the entry "
        "reads back %r, and a later resume would restore nothing for the "
        "boundary that lost it" % sorted(held))
    for attempt_id in (first, second):
        assert held[attempt_id].program_digest == PROGRAM_DIGEST, (
            f"{attempt_id} was admitted under {held[attempt_id].program_digest!r}"
            " rather than the program it was admitted with")
        assert held[attempt_id].status == "held", (
            f"{attempt_id} reads back as {held[attempt_id].status!r}")


def test_admission_is_idempotent_under_repetition(store, investigation):
    """Re-admitting the same operation is one operation, not two.

    The other half of what the column has to survive. A restart re-reads an
    admitted decision and admits it again, so a writer that appended rather
    than matched would grow the list on every restart until the entry no
    longer describes the work it owes.
    """
    from experiments.ad01 import mission

    attempt_id = "p1-att-idem"
    first = _admit(store, investigation, 0, attempt_id)

    again = _admit(store, investigation, 0, attempt_id)

    held = mission.read_in_flight(store, investigation)
    assert len(held) == 1, (
        "re-admitting the same operation grew the list to %d entries: %r"
        % (len(held), [item.attempt_id for item in held]))
    assert again == first, (
        "re-admitting returned a different operation than the first "
        "admission did: %r against %r" % (again, first))
    assert held[0] == first, (
        "re-admitting rewrote the operation already on the entry, so its "
        "recorded identity is the second call's rather than the first's: "
        "%r against %r" % (held[0], first))