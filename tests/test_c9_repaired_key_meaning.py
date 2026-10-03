"""`repaired` means two different things, and no key says which.

`broker.recover` lists every operation it reconciled under `repaired`,
including the ones it could not recover, labelled:

    recovered = ['op-hung:unresolved-liability']

`agenda.repair_scan` and `broker.heartbeat` walk the same
`restart_reconciliation` source over the same stranded operation and report:

    repaired = []      next = 'idle'

while the operation is left `dispatch=unresolved reconcile=unresolved
settled=False`. The exclusion is deliberate, since `1958950`: the
`unresolved-liability` decision means nothing was recovered, so listing it as
a repair would claim a settlement that did not happen. That reasoning is
correct. The defect is that the disagreement is only in the name's meaning,
and nothing at the read site distinguishes the two producers.

So this file pins the divergence rather than resolves it. The fix is in
`src/settlement/broker.py`, which this lane is not permitted to touch, and the
two available repairs are not equivalent:

  - Rename `HeartbeatReport.repaired`. The census is 1 field, 3 in-repo
    writers, 2 in-repo readers (`src/settlement/api.py:403`,
    `scripts/scheduler.py:37`), 11 test assertions, and 2 tests that pin the
    asymmetry itself (`test_inv_b2_loop.py:143` and `:150` assert the two
    producers return different values for the same operation). A rename that
    touches only the field leaves `api.py` and `scheduler.py` publishing the
    ambiguous name unchanged, which is the half-finished state a previous lane
    in this project reverted a rename for.

  - Document it. `sweep` already carries a docstring at
    `src/settlement/broker.py:1133` saying an operation joins `repaired` only
    when the sweep transitioned its durable state. What is missing is the
    statement that `recover` does not hold itself to that, and the census
    above is the evidence for it.

A consumer that reads `repaired` as "operations this scan settled" is wrong
for `recover` and right for `repair_scan`, `heartbeat` and
`scheduler.run_once`, and the report does not say which one answered.
"""

from __future__ import annotations

import sys
from pathlib import Path

import psycopg
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from tests.conftest_isolation import admin_dsn, dsn_with_dbname  # noqa: E402

from settlement import agenda, broker, store
from settlement.common import Command

DATABASE = "v3c9_repaired_key"
DSN = dsn_with_dbname(admin_dsn(), DATABASE)
MIGRATIONS = ROOT / "migrations"


@pytest.fixture()
def dsn():
    from settlement import db

    admin = psycopg.connect(admin_dsn(), autocommit=True)
    admin.execute("DROP DATABASE IF EXISTS %s" % DATABASE)
    admin.execute("CREATE DATABASE %s" % DATABASE)
    admin.close()
    db.apply_migrations(DSN, MIGRATIONS)
    with db.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public'"
                " AND tablename != 'schema_migrations'")
            for (table,) in cur.fetchall():
                cur.execute('TRUNCATE TABLE "%s" CASCADE' % table)
        conn.commit()
    yield DSN
    admin = psycopg.connect(admin_dsn(), autocommit=True)
    admin.execute("DROP DATABASE IF EXISTS %s" % DATABASE)
    admin.close()


def _stranded(dsn: str, operation_id: str) -> None:
    """An operation stuck at `dispatching` with no launcher to recover it.

    `reconcile` returns `unresolved-liability` for it, which is the decision
    `recover` reports and `sweep` skips.
    """
    store.seed_allocation(dsn, Command(
        request_id="c9-alloc", payload={
            "allocation_id": "a1", "domain": "cpu", "authorized": 100}))
    store.prepare_operation(dsn, Command(
        request_id="c9-prep-%s" % operation_id, payload={
            "operation_id": operation_id, "allocation_id": "a1",
            "operation": {"effect": "note"}}))
    store.advance_dispatch(dsn, Command(
        request_id="c9-adv-%s" % operation_id,
        payload={"operation_id": operation_id}))


def test_recover_reports_an_unresolved_liability_under_a_label(dsn) -> None:
    _stranded(dsn, "op-hung")

    report = broker.recover(dsn, {})

    assert report.repaired == ["op-hung:unresolved-liability"]
    assert report.next_decision == "recovered-1-ops-0-attempts"


def test_repair_scan_reports_nothing_for_the_same_operation(dsn) -> None:
    _stranded(dsn, "op-hung")

    report = agenda.repair_scan(dsn, {})

    assert report.repaired == []
    assert report.next_decision == "idle"


def test_the_two_producers_disagree_about_one_settled_operation(dsn) -> None:
    """The defect, as a single pair of assertions on the same state.

    Both walk `restart_reconciliation`. One of them is reporting an operation
    that is still holding its exposure.
    """
    _stranded(dsn, "op-hung")

    scanned = agenda.repair_scan(dsn, {})
    recovered = broker.recover(dsn, {})
    row = broker.read_operation(dsn, "op-hung")

    assert (row["dispatch_state"], row["reconcile_state"], row["settled"]) \
        == ("unresolved", "unresolved", False)
    assert recovered.repaired == ["op-hung:unresolved-liability"]
    assert scanned.repaired == []


def test_the_reported_entry_is_not_an_operation_id(dsn) -> None:
    """`repaired` holds a bare id in one producer and a labelled pair in the
    other, so a consumer cannot tell which shape it received by value alone."""
    _stranded(dsn, "op-hung")

    recovered = broker.recover(dsn, {})
    scanned = agenda.repair_scan(dsn, {})

    assert recovered.repaired[0] == "op-hung:unresolved-liability"
    assert "op-hung" in recovered.repaired[0]
    assert scanned.repaired == []


def test_the_exclusion_is_deliberate_rather_than_a_defect(dsn) -> None:
    """The scan's silence is the correct behaviour; only the name is wrong.

    `broker.py:1211` skips `unresolved-liability` so a caller is not told an
    operation settled when it is still holding exposure. A reader of this test
    should conclude the fix belongs in the key's meaning, not in the scan.
    """
    _stranded(dsn, "op-hung")

    agenda.repair_scan(dsn, {})
    row = broker.read_operation(dsn, "op-hung")

    assert row["settled"] is False
    assert row["dispatch_state"] == "unresolved"


def test_the_rename_would_be_partial_across_three_surfaces(dsn) -> None:
    """The census that decides between renaming and documenting.

    If `HeartbeatReport.repaired` were renamed, the field would move inside
    `broker.py` while two in-repo publishers kept the old name on the wire:
    the `repair` command's `data` in `src/settlement/api.py:403` and the
    scheduler's JSON in `scripts/scheduler.py:37`. Both carry the same
    ambiguous name to the same kind of consumer, which is precisely the reader
    the defect is about.
    """
    import ast

    field = ast.parse(
        (ROOT / "src/settlement/broker.py").read_text(encoding="utf-8"))
    report = next(node for node in ast.walk(field)
                  if isinstance(node, ast.ClassDef)
                  and node.name == "HeartbeatReport")
    names = [item.target.id for item in report.body
             if isinstance(item, ast.AnnAssign)
             and isinstance(item.target, ast.Name)]

    assert "repaired" in names
    for path, line in (("src/settlement/api.py", 403),
                       ("scripts/scheduler.py", 37)):
        text = (ROOT / path).read_text(encoding="utf-8").splitlines()
        assert '"repaired"' in text[line - 1], path
