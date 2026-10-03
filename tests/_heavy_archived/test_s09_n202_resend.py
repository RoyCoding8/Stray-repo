"""N-202 re-send half: a stranded dispatch is re-sent, not replaced.

The ledger half of N-202 is closed; this file covers the other half. A kill
between `advance_dispatch` and the launcher's spawn leaves an operation in
`dispatching`, holding a reservation, with no receipt and no worker. That
operation is not lost work, and `_durable_receipt` used to refuse it as
"conflicted or unresolved" before the broker was ever asked, so the caller
scored a validation failure and the campaign spent a fresh
`repair-transport` construction call against it.

The broker already implements the recovery for exactly this state
(`_resume_dispatching` to `redispatch_after_reset`, gated on a
capability-backed never-sent proof). The fix belongs in the refusal, not in
the broker and not in the replacement path.

The refusal stays strict everywhere else. An operation that is genuinely
conflicted, genuinely unresolved, or genuinely already sent must still be
refused, because reclaiming those is a double-execution bug. Each of those
has a test below, so loosening the one reclaimable state is pinned against
the three it must not swallow.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from settlement import broker, store
from settlement.common import Command, ResultCode
from settlement.launcher_local import LocalLauncher

MIGRATIONS = ROOT / "migrations"
RUN_TOKEN = "n202resend%s" % uuid.uuid4().hex[:8]
TASK = "ad01-w0-dev-sw-00"

MEMBER_SOURCE = (
    "def carried(task, oracle):\n"
    "    report = oracle.query(task)\n"
    "    return {\"candidate\": {\"source\": \"requested\","
    " \"verdict\": report[\"verdict\"]}, \"queries\": 1}\n"
)


def _create():
    from experiments.ad01.s09_run_isolation import create_disposable_db

    return create_disposable_db(RUN_TOKEN, migrations_dir=MIGRATIONS)


def _drop(database):
    from experiments.ad01.s09_run_isolation import drop_disposable_db

    drop_disposable_db(database)


def _fresh_db(dsn, seq=0):
    from experiments.ad01 import trajectory
    from experiments.coord02 import experience as E

    assert "live" not in dsn
    E.designate_db(dsn, kind="disposable", purpose="n202 resend")
    E.prepare_disposable_db(dsn, MIGRATIONS)
    trajectory.authorize_campaign(
        dsn, trajectory.campaign_id(0, "I", seq), authorized=100000)
def _member():
    return {"capability_id": "n202-resend-member",
            "method_source": MEMBER_SOURCE, "entry": "carried"}


class _Killed(Exception):
    """The dispatcher died. Not a refusal, and not a settlement."""


def _strands_first_dispatch(monkeypatch):
    """Make the first dispatch die between `advance_dispatch` and the spawn.

    This is the kill the defect describes, at the only seam that reproduces
    it without a process race: the operation is admitted with the real
    payload, the dispatch is advanced exactly as the broker does it, and the
    dispatcher then dies rather than returning. No worker, no receipt, no
    launcher marker, and a live reservation.

    The seam is before the launcher, which is the point. A kill here happens
    before the launcher can record anything, so nothing on disk claims the
    work and the operation is reclaimable in the honest case. Later calls
    fall through to the real broker, so the reclaim under test runs
    unmolested.
    """
    real = broker.dispatch_operation
    stranded = []

    def dispatch_operation(dsn, operation_id, **kwargs):
        if stranded:
            return real(dsn, operation_id, **kwargs)
        launchers = kwargs.get("launchers") or {}
        launcher_id = getattr(
            next(iter(launchers.values()), None), "launcher_id", "local-1")
        advanced = store.advance_dispatch(
            dsn, Command(
                request_id="n202-adv-%s" % uuid.uuid4().hex[:12],
                payload={"operation_id": operation_id,
                         "launcher_id": launcher_id or "local-1",
                         "provider_id": ""}))
        assert advanced.code == ResultCode.APPLIED, advanced.detail
        stranded.append(operation_id)
        raise _Killed(operation_id)

    monkeypatch.setattr(broker, "dispatch_operation", dispatch_operation)
    return stranded


def _op_state(dsn, operation_id):
    row = broker.read_operation(dsn, operation_id)
    return row["dispatch_state"], len(store.operation_receipts(dsn, operation_id))


def test_a_stranded_dispatch_is_reclaimed_rather_than_refused(tmp_path, monkeypatch):
    """The defect itself: a receipt-less `dispatching` op must not be refused.

    `_durable_receipt` raised for any unsettled operation that was not
    `prepared`, which is the stranded operation's own state. The refusal
    arrived before `broker.dispatch_operation`, so the never-sent proof and
    the re-send path below it were never entered, and the campaign replaced
    the lineage instead.

    Re-running the same member for the same operation must now execute the
    original operation, settle it, and return the result the control run
    returned, with the operation's own id and no second operation minted.
    """
    from experiments.ad01 import method_exec, trajectory, worlds

    ledger = tmp_path / "claims.jsonl"
    monkeypatch.setenv("SETTLEMENT_CLAIM_LEDGER", str(ledger))

    database = _create()
    try:
        dsn = database.dsn
        _fresh_db(dsn, 40)
        cid = trajectory.campaign_id(0, "I", 40)
        allocation_id = trajectory._alloc_id(cid)
        operation_id = "ad01-%s-member-k0" % cid
        task = worlds.load_task(worlds.FROZEN_DIR, TASK)

        stranded = _strands_first_dispatch(monkeypatch)
        with pytest.raises(_Killed):
            method_exec.run_member_out_of_process(
                _member(), task, dsn=dsn, allocation_id=allocation_id,
                operation_id=operation_id)
        assert stranded == [operation_id]

        assert _op_state(dsn, operation_id) == ("dispatching", 0)
        before = broker.read_operation(dsn, operation_id)["payload"]
        stranded_generation = before["_dispatch_generation"]

        result = method_exec.run_member_out_of_process(
            _member(), task, dsn=dsn, allocation_id=allocation_id,
            operation_id=operation_id)

        assert result["operation_id"] == operation_id
        assert result["operation_ids"] == [operation_id]
        assert result["candidate"] == {"source": "requested",
                                       "verdict": "preserved"}

        state, receipts = _op_state(dsn, operation_id)
        assert receipts == 1, (state, receipts)
        assert state in ("sent", "observed"), state

        after = broker.read_operation(dsn, operation_id)["payload"]
        assert after["_dispatch_generation"] > stranded_generation, after

        rows = _rows(dsn, "SELECT id FROM operations ORDER BY id")
        assert rows == [operation_id], rows
    finally:
        _drop(database)


def test_the_reclaimed_operation_settles_its_reservation(tmp_path, monkeypatch):
    """A re-sent operation that produces no receipt would move the leak.

    The 111 units were stranded because nothing would ever settle them. The
    recovery is only the leak's cure if the re-sent operation reaches a
    receipt, which is what returns the reservation to the allocation.
    """
    from experiments.ad01 import method_exec, trajectory, worlds

    ledger = tmp_path / "claims.jsonl"
    monkeypatch.setenv("SETTLEMENT_CLAIM_LEDGER", str(ledger))

    database = _create()
    try:
        dsn = database.dsn
        _fresh_db(dsn, 41)
        cid = trajectory.campaign_id(0, "I", 41)
        allocation_id = trajectory._alloc_id(cid)
        operation_id = "ad01-%s-member-k0" % cid
        task = worlds.load_task(worlds.FROZEN_DIR, TASK)

        _strands_first_dispatch(monkeypatch)
        with pytest.raises(_Killed):
            method_exec.run_member_out_of_process(
                _member(), task, dsn=dsn, allocation_id=allocation_id,
                operation_id=operation_id)

        held = _reserved(dsn)
        assert held > 0, "a stranded operation leaked no units to recover"

        method_exec.run_member_out_of_process(
            _member(), task, dsn=dsn, allocation_id=allocation_id,
            operation_id=operation_id)

        assert _reserved(dsn) == 0
    finally:
        _drop(database)


def test_a_conflicted_operation_is_still_refused(tmp_path, monkeypatch):
    """The looseness is scoped to one state, and this is the edge of it.

    `conflict` means two receipts disagree about what happened. No proof of
    never-sent can be true about it, and re-sending would execute work that
    already produced a result.
    """
    from experiments.ad01 import method_exec, trajectory, worlds

    ledger = tmp_path / "claims.jsonl"
    monkeypatch.setenv("SETTLEMENT_CLAIM_LEDGER", str(ledger))

    database = _create()
    try:
        dsn = database.dsn
        _fresh_db(dsn, 42)
        cid = trajectory.campaign_id(0, "I", 42)
        allocation_id = trajectory._alloc_id(cid)
        operation_id = "ad01-%s-member-k0" % cid
        task = worlds.load_task(worlds.FROZEN_DIR, TASK)

        _strands_first_dispatch(monkeypatch)
        with pytest.raises(_Killed):
            method_exec.run_member_out_of_process(
                _member(), task, dsn=dsn, allocation_id=allocation_id,
                operation_id=operation_id)
        _mark(dsn, operation_id, "reconcile_state", "conflict")

        with pytest.raises(method_exec.MethodExecutionError,
                           match="conflicted or unresolved"):
            method_exec.run_member_out_of_process(
                _member(), task, dsn=dsn, allocation_id=allocation_id,
                operation_id=operation_id)
    finally:
        _drop(database)


def test_an_unresolved_operation_is_still_refused(tmp_path, monkeypatch):
    """`unresolved` is a reconciliation verdict, not a crash artefact.

    A store that set it did so by deciding the outcome cannot be established
    from the evidence. Re-sending is a fresh execution, which is precisely
    the decision that verdict withheld.
    """
    from experiments.ad01 import method_exec, trajectory, worlds

    ledger = tmp_path / "claims.jsonl"
    monkeypatch.setenv("SETTLEMENT_CLAIM_LEDGER", str(ledger))

    database = _create()
    try:
        dsn = database.dsn
        _fresh_db(dsn, 43)
        cid = trajectory.campaign_id(0, "I", 43)
        allocation_id = trajectory._alloc_id(cid)
        operation_id = "ad01-%s-member-k0" % cid
        task = worlds.load_task(worlds.FROZEN_DIR, TASK)

        _strands_first_dispatch(monkeypatch)
        with pytest.raises(_Killed):
            method_exec.run_member_out_of_process(
                _member(), task, dsn=dsn, allocation_id=allocation_id,
                operation_id=operation_id)
        _mark(dsn, operation_id, "dispatch_state", "unresolved")

        with pytest.raises(method_exec.MethodExecutionError,
                           match="conflicted or unresolved"):
            method_exec.run_member_out_of_process(
                _member(), task, dsn=dsn, allocation_id=allocation_id,
                operation_id=operation_id)
    finally:
        _drop(database)


def test_a_receipted_operation_is_replayed_rather_than_re_sent(tmp_path, monkeypatch):
    """The double-execution guard, in the state that could cause it.

    A `dispatching` operation holding a receipt already ran. The fix makes
    the refusal permissive for a receipt-less `dispatching` operation, so
    what keeps this one from executing twice is the receipt itself: the
    admission path returns the stored receipt before the broker is asked to
    dispatch anything.

    So the assertion is that a second call returns the first call's result
    and adds no receipt, not that it raises. Refusing here would be
    over-tightening, and the fixture below counts spawns to prove nothing
    was launched the second time.
    """
    from experiments.ad01 import method_exec, trajectory, worlds

    monkeypatch.setenv("SETTLEMENT_CLAIM_LEDGER",
                       str(tmp_path / "claims.jsonl"))
    database = _create()
    try:
        dsn = database.dsn
        _fresh_db(dsn, 44)
        cid = trajectory.campaign_id(0, "I", 44)
        allocation_id = trajectory._alloc_id(cid)
        operation_id = "ad01-%s-member-k0" % cid
        task = worlds.load_task(worlds.FROZEN_DIR, TASK)

        first = method_exec.run_member_out_of_process(
            _member(), task, dsn=dsn, allocation_id=allocation_id,
            operation_id=operation_id)
        spawns = _spawns(operation_id)
        assert spawns == 1, spawns
        _mark(dsn, operation_id, "dispatch_state", "dispatching")

        assert _op_state(dsn, operation_id)[1] == 1
        second = method_exec.run_member_out_of_process(
            _member(), task, dsn=dsn, allocation_id=allocation_id,
            operation_id=operation_id)

        assert second["candidate"] == first["candidate"] == {
            "source": "requested", "verdict": "preserved"}
        assert second["queries"] == first["queries"]
        assert _op_state(dsn, operation_id)[1] == 1
        assert _spawns(operation_id) == 1, "a second launch ran"
    finally:
        _drop(database)


def test_a_claim_blocks_the_proof_that_would_authorize_a_re_send(tmp_path, monkeypatch):
    """N-201's half of the argument, asserted from this side.

    The refusal is now permissive for a stranded operation, so the only
    thing standing between a stranded operation and a double execution is
    the claim ledger. This drives the broker's own reclaim path with a real
    claim in place and requires it to refuse. If this test ever starts
    passing the reclaim, the deferral's objection was right and this fix
    trades a 111-unit leak for a double execution.
    """
    from experiments.ad01 import trajectory

    monkeypatch.setenv("SETTLEMENT_CLAIM_LEDGER",
                       str(tmp_path / "claims.jsonl"))
    launcher = LocalLauncher(tmp_path / "runs")
    database = _create()
    try:
        dsn = database.dsn
        _fresh_db(dsn, 45)
        allocation_id = trajectory._alloc_id(
            trajectory.campaign_id(0, "I", 45))
        operation_id = "n202-claimed"
        broker.ensure_operation(
            dsn, operation_id=operation_id, effect=broker.SANDBOX_EXEC,
            payload={"profile": "local-process",
                     "argv": [sys.executable, "-c", "pass"],
                     "timeout_ms": 10_000},
            allocation_id=allocation_id)
        advanced = store.advance_dispatch(
            dsn, Command(request_id="n202-adv-%s" % uuid.uuid4().hex[:12],
                         payload={"operation_id": operation_id,
                                  "launcher_id": launcher.launcher_id,
                                  "provider_id": ""}))
        assert advanced.code == ResultCode.APPLIED, advanced.detail
        generation = int(broker.read_operation(
            dsn, operation_id)["payload"]["_dispatch_generation"])
        assert launcher.claimed(operation_id, generation) is False
        assert launcher._append_claim(
            operation_id=operation_id, dispatch_generation=generation,
            execution_version="") is True
        assert launcher.prove_never_sent(operation_id, generation) is False

        status = broker.redispatch_after_reset(
            dsn, operation_id, {"local-process": launcher}, generation)

        assert status.next_decision == "refused-never-sent-proof", status
        assert _op_state(dsn, operation_id) == ("dispatching", 0)
    finally:
        _drop(database)


def _rows(dsn, sql):
    from settlement import db

    with db.connect(dsn) as conn:
        return [row[0] for row in conn.execute(sql).fetchall()]


def _spawns(operation_id):
    """How many workers the launcher was actually asked to start.

    The launcher's own counter, read from the staging tree it wrote. It is
    the only count that distinguishes a re-send from a replay: two
    executions means this file says 2.

    The staging tree is keyed by dsn, and every prior run of this file left
    a directory behind, so the newest one is this run's.
    """
    from settlement.launcher_local import _sanitize

    name = "%s_exec-default.spawns" % _sanitize(operation_id)
    found = sorted((Path(ROOT) / ".ad01-runs").glob("*/launcher/" + name),
                   key=lambda p: p.stat().st_mtime)
    assert found, operation_id
    return int(found[-1].read_text().strip())


def _reserved(dsn):
    """Units still held against the allocation, which is the leak itself.

    The reservation row keeps its `amount` after settling; it is
    `allocations.reserved` that a stranded operation leaves elevated and
    that a settled one returns to zero. That is the number the 111 units
    were.
    """
    from settlement import db

    with db.connect(dsn) as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(reserved), 0) FROM allocations").fetchone()
    return int(row[0])


def _mark(dsn, operation_id, column, value):
    from settlement import db

    assert column in ("dispatch_state", "reconcile_state"), column
    with db.connect(dsn) as conn:
        conn.execute(
            "UPDATE operations SET %s = %%s WHERE id = %%s"
            % column, (value, operation_id))
