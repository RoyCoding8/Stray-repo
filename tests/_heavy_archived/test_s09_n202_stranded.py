"""N-202: reconciliation cannot see exposure that can never settle.

A kill between `advance_dispatch` and the launcher's spawn leaves an
operation in `dispatching` holding a `reserved` reservation and carrying
no receipt. That exposure is not pending: nothing owns it, so nothing will
ever settle it, and the units stay held against the study for good.

`verify_ledger` folded that amount into `pending` on both sides of its own
arithmetic, so a study holding 111 units that will never settle reported
`match: true`. The self-check gave an all-clear on a real and permanent
loss, which is the worse half of this defect: the resume path that
mints a replacement lineage is visible in the campaign summary, but a
clean ledger is what a reviewer reads to decide nothing was lost.

These tests drive the settlement store directly. The stranded shape is
constructed by advancing an operation's dispatch and then killing the
dispatcher before it reaches a launcher, which is what the live kill
produces; staging it through the campaign is slow and racy, and the
ledger does not care how the shape was reached.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from settlement import authority, broker, db, store
from settlement.common import Command, ResultCode
from settlement.launcher_local import LocalLauncher

MIGRATIONS = ROOT / "migrations"
RUN_TOKEN = "n202%s" % uuid.uuid4().hex[:8]
STUDY = "study-n202"


def _create():
    from experiments.ad01.s09_run_isolation import create_disposable_db

    return create_disposable_db(RUN_TOKEN, migrations_dir=MIGRATIONS)


def _drop(database):
    from experiments.ad01.s09_run_isolation import drop_disposable_db

    drop_disposable_db(database)


def _fresh_db(dsn):
    assert "live" not in dsn
    db.apply_migrations(dsn, MIGRATIONS)
    authority.authorize_study(dsn, STUDY, authorized=10_000)


def _cmd(payload):
    return Command(request_id="req_%s" % uuid.uuid4().hex[:12], payload=payload)


def _admit_sandbox(dsn, operation_id):
    return authority.admit_study_call(
        dsn, STUDY, kind="development", operation_id=operation_id,
        effect=broker.SANDBOX_EXEC,
        payload={"profile": "local-process",
                 "argv": [sys.executable, "-c", "pass"],
                 "timeout_ms": 10_000, "max_output_bytes": 1024})


def _strand(dsn, operation_id):
    """Leave an operation dispatched to a launcher that never spawned it.

    This is the state a kill between `advance_dispatch` and spawn produces:
    the launcher holds the admission, the worker does not exist, and no
    receipt was ever written.
    """
    advanced = store.advance_dispatch(
        dsn, _cmd({"operation_id": operation_id, "launcher_id": "local-1",
                   "provider_id": ""}))
    assert advanced.code == ResultCode.APPLIED, advanced.detail


def test_ledger_reports_stranded_exposure_rather_than_an_all_clear():
    database = _create()
    try:
        dsn = database.dsn
        _fresh_db(dsn)
        _admit_sandbox(dsn, "n202-stranded")
        _strand(dsn, "n202-stranded")

        ledger = authority.verify_ledger(dsn, STUDY)

        assert ledger["unreceipted"] == ["n202-stranded"]
        assert ledger["pending"] > 0
        assert ledger["reserved"] == ledger["pending"]
        assert ledger["stranded"] == {"n202-stranded": ledger["pending"]}
        assert ledger["match"] is False
    finally:
        _drop(database)


def test_stranded_exposure_does_not_hide_behind_a_settled_neighbour():
    """A settled operation beside a stranded one must not launder it.

    The two operations are independent, and the stranded one is the one
    that never settles. Arithmetic that only ever compared totals would let
    the settled neighbour vouch for it.
    """
    database = _create()
    try:
        dsn = database.dsn
        _fresh_db(dsn)
        _admit_sandbox(dsn, "n202-settled")
        _admit_sandbox(dsn, "n202-stranded")
        launcher = LocalLauncher(Path(os.environ.get("N202_TMP", "/tmp")) /
                                 "n202-settled-runs")
        launchers = {"local-process": launcher}
        status = broker.dispatch_operation(dsn, "n202-settled",
                                          launchers=launchers)
        if status.next_decision == "needs-reconciliation":
            decision = broker.reconcile(dsn, "n202-settled", launchers)
            assert decision.decision == "receipt-admitted", decision.detail
        _strand(dsn, "n202-stranded")

        ledger = authority.verify_ledger(dsn, STUDY)

        assert ledger["unreceipted"] == ["n202-stranded"]
        assert ledger["stranded"] == {"n202-stranded": ledger["pending"]}
        assert ledger["match"] is False
    finally:
        _drop(database)


def test_a_prepared_operation_is_not_stranded():
    """Prepared work has not been dispatched, so its exposure still settles.

    It is pending exposure held against a reservation that a dispatch will
    consume. Reporting it as stranded would make a healthy study
    unreportable, and the distinction is the whole point of the key.
    """
    database = _create()
    try:
        dsn = database.dsn
        _fresh_db(dsn)
        _admit_sandbox(dsn, "n202-prepared")

        ledger = authority.verify_ledger(dsn, STUDY)

        assert ledger["unreceipted"] == ["n202-prepared"]
        assert ledger["stranded"] == {}
        assert ledger["match"] is True
    finally:
        _drop(database)


def test_a_receipted_operation_is_not_stranded():
    """A decided operation's exposure is settled, stranded or not."""
    database = _create()
    try:
        dsn = database.dsn
        _fresh_db(dsn)
        _admit_sandbox(dsn, "n202-decided")
        launcher = LocalLauncher(Path(os.environ.get("N202_TMP", "/tmp")) /
                                 "n202-decided-runs")
        launchers = {"local-process": launcher}
        status = broker.dispatch_operation(dsn, "n202-decided",
                                          launchers=launchers)
        if status.next_decision == "needs-reconciliation":
            decision = broker.reconcile(dsn, "n202-decided", launchers)
            assert decision.decision == "receipt-admitted", decision.detail
        assert broker.read_operation(dsn, "n202-decided")["dispatch_state"] \
            in ("observed", "reconciled")

        ledger = authority.verify_ledger(dsn, STUDY)

        assert ledger["stranded"] == {}
        assert ledger["unreceipted"] == []
        assert ledger["match"] is True
    finally:
        _drop(database)
