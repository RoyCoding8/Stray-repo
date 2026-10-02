"""C3: the E3 store witness counts the operations the run actually wrote.

`operations_written_by_the_run` was the difference between two
`SELECT count(*) FROM operations` totals, one taken before the run and one
after. A table total is every writer in the interval between the two
snapshots, and this store is shared: a concurrent lane's operation enters
the same difference as the run's own work.

The number that field carries is load-bearing. `test_s09_e3_sever`
compares it against the run's decision count and requires equality, so a
foreign row either inflates the count and fails a correct run, or, on a
run that made one fewer decision than its neighbour, silently supplies
the difference and passes a run that wrote nothing for that decision. The
second is the dangerous direction, and it is the one an unscoped count can
produce without anyone noticing.

Scoping is to the run's own operation ids, which is the key that actually
bounds a run. The recorder's operation id is `ad01-<campaign>-op<seq>-...`
and `_default_campaign` is uuid-derived per run, so no other run can
produce one of these ids. The command journal's `request_id` is not usable
here: the recorder builds a fresh uuid per settlement call rather than
carrying the run's identity, so a request id bounds a call, not a run.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from experiments.ad01 import agenda_policy
from experiments.ad01 import s09_e3_selection as e3


def _foreign_operation(dsn: str, tag: str) -> str:
    """One operation row this run did not write.

    Written the way any other lane's dispatcher writes one: a real row,
    through the table the witness counts.
    """
    from settlement import db

    operation_id = "c3-foreign-%s-%s" % (tag, uuid.uuid4().hex[:8])
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO operations (id, allocation_id, payload_digest,"
                " payload, dispatch_state) VALUES (%s, NULL, %s, %s,"
                " 'prepared')",
                (operation_id, "0" * 64, '{"written_by": "somebody else"}'))
        conn.commit()
    return operation_id


def _witness_with_a_concurrent_writer(dsn: str, tag: str) -> tuple[dict, str]:
    """Run the witness while another writer commits inside its window.

    The witness measures its count between the run finishing and its own
    read-back. Wrapping `run_policy` places a foreign commit exactly
    there, which is where a concurrent lane on a shared store commits
    one. Injecting before or after the whole witness call would miss
    the window entirely and pass against the unscoped count, which is
    what the first version of this test did.
    """
    real_run_policy = e3.run_policy

    def racing_run_policy(*args, **kwargs):
        run = real_run_policy(*args, **kwargs)
        _foreign_operation(dsn, tag)
        return run

    e3.run_policy = racing_run_policy
    try:
        return e3.store_witness(dsn, world=0, budget=40), tag
    finally:
        e3.run_policy = real_run_policy


def test_a_concurrent_operation_inside_the_window_is_not_counted_as_the_runs(migrated_db):
    """The regression itself: the count must ignore a row the run did not write.

    The foreign commit lands between the run finishing and the witness
    reading the table back, so an unscoped before/after difference
    charges it to this run.
    """
    dsn = migrated_db
    run, tag = _witness_with_a_concurrent_writer(dsn, "race")
    decided = len(run["run_decisions"])
    assert decided, "the run made no decisions, so this asserts nothing"

    run_ids = {record["operation_id"] for record in run["bindings"]}
    foreign = [row for row in run["receipts"]
               if row["operation_id"].startswith("c3-foreign-%s-" % tag)]
    assert not foreign, "the witness read back a foreign operation's receipt"

    assert run["operations_written_by_the_run"] == decided, (
        "the run made %d decisions and reported %d operations, with a "
        "concurrent writer's row inside the measurement window"
        % (decided, run["operations_written_by_the_run"]))
    assert all(operation_id in run_ids
               for operation_id in (r["operation_id"] for r in run["bindings"]))
    assert not any(operation_id.startswith("c3-foreign-")
                   for operation_id in run_ids)


def test_the_count_is_scoped_to_the_runs_own_ids(migrated_db):
    """The scope is the run's ids, so a direct count of them agrees.

    This pins the key rather than the outcome. A count scoped to
    something else that happened to agree in the first test would
    satisfy that one and not this.
    """
    dsn = migrated_db
    run = e3.store_witness(dsn, world=0, budget=40)
    operation_ids = [record["operation_id"] for record in run["bindings"]]
    assert operation_ids, "the run bound no operations"

    assert e3._operations_for_ids(dsn, operation_ids) == \
        run["operations_written_by_the_run"]
    assert e3._operations_for_ids(dsn, []) == 0
    assert e3._operations_for_ids(dsn, ["no-such-operation"]) == 0

    _foreign_operation(dsn, "scoped")
    assert e3._operations_for_ids(dsn, operation_ids) == \
        run["operations_written_by_the_run"], (
        "a foreign row changed the count over the run's own ids")


def test_a_severed_run_reports_zero(migrated_db):
    """The severed arm has no ids, so the count is zero by construction.

    A severed run is refused before the recorder and produces no
    operations, so its id list is empty. This asserts the empty case
    answers 0 rather than raising or falling back to a table total.
    """
    run = e3.store_witness(migrated_db, world=0, budget=40, sever=True)

    assert run["bindings"] == []
    assert run["operations_written_by_the_run"] == 0
