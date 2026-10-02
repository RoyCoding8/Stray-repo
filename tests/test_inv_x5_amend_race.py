"""Concurrent amends of one protocol must resolve to one successor.

`amend_protocol` read the superseded protocol on one connection, committed,
closed it, built the replacement through `freeze_protocol` on a third
transaction, and only then wrote `supersedes` and `frozen` on a fourth
connection with `autocommit=True`. Nothing serialised the read that decided
the write against the write itself, so four concurrent amends of one parent
all applied and left four frozen children claiming the same parent.

This is the fifth defect of one shape. Across two search passes and the
independent review, every defect found was a lock taken on a row the writer
may not have created, or a read and a write split across connections. A
census asking "does this writer lock?" passes all five, because in each the
lock is on the wrong row or the deciding read happened somewhere else. The
census that finds them asks whether the lock and the read-modify-write cover
the same rows in the same transaction.

Two outcomes were available and only one is correct here.

Refusing every loser outright is not available. `experiment.run_abcs` amends
one parent into four distinct children on purpose
(`src/settlement/experiment.py:1147-1153` loops `panel-B`, `panel-C`,
`transfer-B`, `transfer-C` over the same `eval_pid`), and
`tests/test_dev02_episode.py:270` runs that path. Four siblings of one panel
protocol is the designed shape, so "one parent, one successor forever" would
narrow a live operation, and requirement 4 forbids that.

So the amends serialise. Each amend takes `FOR UPDATE` on the parent row
inside the same transaction that inserts its own child, which is the lock
whose absence made the race possible, and the child row is inserted already
naming its parent rather than being stamped afterwards.

The loser of a genuine race is refused rather than absorbed. The test is a
race, not a lag: a caller that read the parent and then waited behind another
amend's lock holds a view of the lineage that is no longer current, so it is
told so instead of being answered against a parent whose successor set moved
under it. A caller that arrives strictly after the other amend committed
observed that successor before it locked, so nothing changed under it and it
proceeds. That is why the fix distinguishes a lost race from a legitimate
later amend without asking the caller to serialise itself.

Real PostgreSQL and real threads throughout, because the property is a
property of the transaction. Each was watched failing before the fix.
"""

from __future__ import annotations

import contextlib
import os
import sys
import threading
from pathlib import Path

import pytest
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

MIGRATIONS = ROOT / "migrations"
RUN_TOKEN = "x5amend"

GROUPS = [{"name": "development", "kind": "development"},
          {"name": "visible", "kind": "visible-regression"},
          {"name": "panel", "kind": "protected-eval"}]


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


def _freeze(dsn, protocol_id: str) -> None:
    from settlement import trials
    from settlement.common import Command

    trials.freeze_protocol(
        dsn, Command(request_id=f"x5-frz-{protocol_id}", payload={}),
        protocol_id=protocol_id, candidate_version="cand-0",
        reference_version="ref-0", evaluator_version="eval-0",
        task_groups=GROUPS, budgets={"amortization_horizon": {"tasks": 20}},
        metrics=["success_rate"], stopping={}, exclusions=[], uncertainty={})


def _amend(dsn, protocol_id: str, parent: str, tag: str = ""):
    from settlement import trials
    from settlement.common import Command

    return trials.amend_protocol(
        dsn, Command(request_id=f"x5-amd-{tag or protocol_id}", payload={}),
        protocol_id=protocol_id, supersedes=parent,
        candidate_version=f"cand-{protocol_id}")


def _children(dsn, parent: str) -> list[tuple]:
    """The successor set of `parent`, read straight from the database."""
    from settlement import db

    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, supersedes, frozen FROM trial_protocols"
                        " WHERE supersedes = %s ORDER BY id", (parent,))
            rows = [(row[0], row[1], row[2]) for row in cur.fetchall()]
            conn.commit()
    return rows


def _race(dsn, parent: str, racers: int = 4):
    """Offer `racers` amends of one parent at the same moment."""
    gate = threading.Barrier(racers, timeout=60)
    applied: list = []
    refused: list = []
    lock = threading.Lock()

    def amend(index: int) -> None:
        child = f"{parent}-child-{index}"
        gate.wait()
        try:
            result = _amend(dsn, child, parent, tag=f"race-{parent}-{index}")
        except Exception as exc:  # noqa: BLE001 - collected and asserted below
            with lock:
                refused.append((child, type(exc).__name__, str(exc)))
            return
        with lock:
            applied.append((child, result.code.value, result.detail))

    threads = [threading.Thread(target=amend, args=(i,)) for i in range(racers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=180)
    assert not any(thread.is_alive() for thread in threads), (
        "an amend thread never finished, so the race was not exercised")
    return applied, refused


def test_four_concurrent_amends_of_one_parent_leave_one_successor(store):
    """Four amends offered together resolve to exactly one successor.

    The count is read back from `trial_protocols` rather than from the return
    values, because the durable row is what a reader consults to find the
    successor. Before the fix this parent held four frozen children.
    """
    parent = "x5-one-successor"
    _freeze(store, parent)

    applied, refused = _race(store, parent)

    successors = _children(store, parent)
    assert len(successors) == 1, (
        f"four concurrent amends of {parent} left {len(successors)} children "
        f"{[row[0] for row in successors]}; {len(applied)} applied and "
        f"{len(refused)} were refused. `supersedes` is the row a reader uses "
        "to find the successor, and four of them answer the wrong question")

    child, frozen_child, frozen = successors[0]
    assert child in [name for name, _, _ in applied], (
        f"the child on disk {child!r} is not one of the calls that applied: "
        f"{[name for name, _, _ in applied]}")
    assert frozen is True, (
        f"successor {child} of {parent} is not frozen; an unfrozen protocol "
        "refuses every assignment against it")


def test_a_losing_amend_is_refused_with_a_reason_and_never_shaped_as_success(store):
    """The loser is told, in a shape that cannot be read as an apply.

    An amend is an operator action, so an operator who lost the race must be
    able to tell. A loser raises rather than returning a `CommandResult`, and
    it leaves no child row behind, so nothing about it is silently dropped and
    nothing about it looks like the success shape an applied amend returns.
    """
    parent = "x5-loser-refused"
    _freeze(store, parent)

    applied, refused = _race(store, parent)

    assert len(applied) == 1, (
        f"{len(applied)} amends of {parent} returned a success shape "
        f"{applied}; a race has one winner")
    assert len(refused) == 3, (
        f"expected 3 refused amends, got {len(refused)}: {refused}")

    for child, name, reason in refused:
        assert name == "StaleRevision", (
            f"loser {child} raised {name} rather than a refusal that names "
            f"the lost race: {reason!r}")
        assert parent in reason, (
            f"the refusal for {child} does not name the parent it lost: {reason!r}")
        assert "concurrent" in reason, (
            f"the refusal for {child} gives no reason a caller could act on: "
            f"{reason!r}")
        assert child not in [row[0] for row in _children(store, parent)], (
            f"loser {child} left a child row behind, so the refusal is not the "
            "whole of what happened")

    winner = _children(store, parent)[0][0]
    assert winner not in [child for child, _, _ in refused], (
        f"the durable winner {winner} is also reported as a loser, so the "
        "refusals and the store disagree")


def test_the_deciding_read_and_the_write_share_one_connection(store, monkeypatch):
    """The read that decides the amendment and the row it writes share a
    connection, and the parent is locked for the whole of it.

    The store does not hand a test the identity of the connection a handler
    ran on, so this asserts the three things it can see and names the limit.
    `db.connect` is counted, so the connection count is measured rather than
    inferred. Every statement is recorded in order, so the parent is locked
    before the child is written. And the successor link is written by the
    insert itself, not stamped by a second statement, so a reader can never
    see a frozen child that names no parent.

    Two connections is the count this asserts, and the second is the point
    rather than an allowance. `_observed_successors` reads the parent's
    successor set before the lock, on its own connection, because a caller
    that held the lock before it looked would see the same set the lock
    releases and the comparison could never tell an overtaken caller from a
    later one. The transaction that decides and the row it writes are the
    other connection, and that pair is what the defect split.
    """
    import psycopg

    from settlement import db

    opened: list = []
    statements: list = []
    real_connect = db.connect
    real_execute = psycopg.Cursor.execute

    def spy_connect(dsn, **kwargs):
        conn = real_connect(dsn, **kwargs)
        opened.append(conn)
        return conn

    def spy_execute(self, query, *args, **kwargs):
        statements.append(" ".join(str(query).split()))
        return real_execute(self, query, *args, **kwargs)

    monkeypatch.setattr(db, "connect", spy_connect)
    monkeypatch.setattr(psycopg.Cursor, "execute", spy_execute)

    parent = "x5-one-transaction"
    _freeze(store, parent)
    opened.clear()
    statements.clear()

    _amend(store, f"{parent}-child", parent)

    assert len(opened) == 2, (
        f"one amend opened {len(opened)} connections; it needs exactly two: "
        "the pre-lock observation of the successor set, and the transaction "
        "that decides and writes under the parent lock")

    locks = [i for i, sql in enumerate(statements)
             if "FROM trial_protocols WHERE id = %s FOR UPDATE" in sql]
    writes = [i for i, sql in enumerate(statements)
              if sql.startswith("INSERT INTO trial_protocols")]
    assert locks, f"the parent was never locked: {statements}"
    assert writes, f"no child protocol row was written: {statements}"
    assert locks[0] < writes[0], (
        f"the child was written before the parent was locked: {statements}")
    assert not [sql for sql in statements if "SET supersedes" in sql], (
        "the successor link is still stamped by a separate statement rather "
        f"than written with the child: {statements}")
    assert not any("autocommit=True" in sql for sql in statements), (
        "an amend must not write its lineage on an autocommit connection")


def test_a_plain_freeze_still_stores_the_fields_its_caller_passed(store):
    """The other half of the pair is unchanged, including an explicit empty.

    `freeze_protocol` and `amend_protocol` now resolve their columns through
    one rule. The rule reads a caller's own arguments on the plain path and
    the parent on the amend path, and this checks the plain one rather than
    trusting it: an argument the caller passed as empty stores that empty
    rather than being read as absent. The values are read back from the
    database, not from the arguments.
    """
    from settlement import trials
    from settlement.common import Command

    trials.freeze_protocol(
        store, Command(request_id="x5-plain-freeze", payload={}),
        protocol_id="x5-plain", candidate_version="cand",
        reference_version="ref", evaluator_version="v1",
        task_groups=GROUPS, budgets={}, metrics=["success_rate"],
        stopping={"rule": "fixed-panel"}, exclusions=["slow"],
        uncertainty={"treatment": "finite-panel-only"},
        supported_scope={"family": "software-repair"})

    with _cursor(store) as cur:
        cur.execute("SELECT candidate_version, budgets, metrics, stopping,"
                    " exclusions, uncertainty, supported_scope, frozen,"
                    " supersedes FROM trial_protocols WHERE id = %s",
                    ("x5-plain",))
        row = cur.fetchone()

    assert row["candidate_version"] == "cand"
    assert dict(row["budgets"]) == {}, (
        f"an explicit empty budgets did not store empty: {row['budgets']!r}")
    assert list(row["metrics"]) == ["success_rate"], (
        f"the caller's metrics were dropped: {row['metrics']!r}")
    assert dict(row["stopping"]) == {"rule": "fixed-panel"}
    assert list(row["exclusions"]) == ["slow"]
    assert dict(row["supported_scope"]) == {"family": "software-repair"}
    assert row["frozen"] is True
    assert row["supersedes"] == "", (
        "a plain freeze named a parent it was never given")


@contextlib.contextmanager
def _cursor(dsn: str):
    """One read cursor, so a query and its assertions share a transaction."""
    from settlement import db

    conn = db.connect(dsn)
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            yield cur
        conn.commit()
    finally:
        conn.close()


def test_sequential_amends_of_one_parent_still_all_apply(store):
    """The legitimate operation survives: four children of one parent.

    `run_abcs` builds exactly this shape, four arm protocols off one frozen
    panel protocol, and a fix that made the second one impossible would narrow
    it. The difference from the race is that each caller here observed the
    existing successors before it locked, so nothing moved underneath it.
    """
    from settlement.common import ResultCode

    parent = "x5-sequential-ok"
    _freeze(store, parent)

    results = [_amend(store, f"{parent}-arm-{index}", parent, tag=f"seq-{index}")
               for index in range(4)]

    assert [result.code for result in results] == [ResultCode.APPLIED] * 4, (
        f"sequential amends of one parent stopped applying: "
        f"{[(r.code.value, r.detail) for r in results]}; four arm protocols "
        "off one panel protocol is the shape run_abcs builds")

    successors = _children(store, parent)
    assert [row[0] for row in successors] == \
        [f"{parent}-arm-{index}" for index in range(4)], (
        f"the four sequential children are not all present: {successors}")
    assert all(row[2] is True for row in successors), (
        f"a sequential child came back unfrozen: {successors}")