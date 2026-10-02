"""Two first corrections to one decision key must not both be admitted.

`take_correction` takes `FOR UPDATE` on the `study_corrections` row keyed by
`(study_root, decision_key)`, then reads `used`, then increments it. The lock
is the whole of the protection, and on the first correction there is no row
to lock: `SELECT ... FOR UPDATE` returns nothing and locks nothing, so two
callers arriving together both read `used = 0` and both proceed down the
`INSERT ... ON CONFLICT DO UPDATE SET used = study_corrections.used + 1`
branch.

The increment is a re-read inside the `ON CONFLICT` clause rather than the
`used + 1` computed in Python, so the durable count is right. What is wrong
is the admission: each caller returns `"allowed": used + 1 <= effective` from
its own stale `used`, so a budget of one admits two corrections. The budget
is the ceiling on how many times a learner may be told it was wrong, and it
is spent one over.

This is the same shape as pass 1's `_hold_on_mission_entry` defect and as
this pass's `release_operation` defect: a lock taken on a row that the same
code path may not have created yet. Three separate lanes, one pattern.

`_spend_correction` is the live caller (`loop.py:396`), and it reads `used`
on a separate connection first and passes it as `attempt`, so the stale read
is already on the caller's side of the boundary too.
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

MIGRATIONS = ROOT / "migrations"
RUN_TOKEN = "p2correction"

STUDY_ROOT = "p2-correction-study"


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


def test_two_concurrent_first_corrections_do_not_both_spend_the_budget(store):
    """A budget of one admits exactly one correction.

    Two callers take the same decision key's first correction at the same
    moment. The assertion is literal: exactly one is allowed, and the durable
    counter agrees with the number of admissions. A `FOR UPDATE` on a row that
    does not exist yet locks nothing, so both callers read `used = 0` and both
    return allowed.
    """
    from settlement import authority

    authority.authorize_study(store, STUDY_ROOT, authorized=100000,
                              correction_budget=1)
    decision_key = "p2-concurrent-first-correction"

    gate = threading.Barrier(2, timeout=60)
    results: list = []
    errors: list = []
    lock = threading.Lock()

    def spend() -> None:
        try:
            gate.wait()
            taken = authority.take_correction(
                store, STUDY_ROOT, decision_key, {"reason": "p2 probe"},
                attempt=1, budget=1)
        except Exception as exc:  # noqa: BLE001 - collected and asserted below
            with lock:
                errors.append((type(exc).__name__, str(exc)))
            return
        with lock:
            results.append(taken)

    threads = [threading.Thread(target=spend) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    assert not any(thread.is_alive() for thread in threads), (
        "a correction thread never finished, so the race was not exercised")

    assert errors == [], f"a correction raised rather than racing cleanly: {errors}"

    admitted = [row for row in results if row["allowed"]]
    assert len(admitted) == 1, (
        "a budget of one admitted "
        f"{len(admitted)} corrections: {[r['allowed'] for r in results]}; "
        "the correction budget is the ceiling on how many times a learner is "
        "told it was wrong")

    durable = authority.correction_state(store, STUDY_ROOT, decision_key)
    assert int(durable["used"]) == len(admitted), (
        f"the durable counter reads {durable['used']} against {len(admitted)} "
        "admissions, so the store and the answer disagree")