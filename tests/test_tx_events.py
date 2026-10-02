from __future__ import annotations

import threading
import time
import uuid

from settlement import db, store
from settlement.common import Command, ResultCode


def _cmd(payload: dict, **kw) -> Command:
    return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload, **kw)


def test_epochs_increase_and_ordinals_reset_per_transition(migrated_db):
    dsn = migrated_db
    store.seed_allocation(dsn, _cmd({"allocation_id": "a1", "domain": "cpu", "authorized": 10}))
    store.admit_commitment(dsn, _cmd({"investigation_id": "i1", "objective": "o"}))
    got = store.read_events(dsn)
    assert [(e["epoch"], e["ordinal"]) for e in got["events"]] == [(1, 0), (2, 0)]
    assert (got["cursor_epoch"], got["cursor_ordinal"]) == (2, 0)


def test_cursor_pagination_collects_everything(migrated_db):
    dsn = migrated_db
    for n in range(5):
        store.seed_allocation(dsn, _cmd({"allocation_id": f"a{n}", "domain": "cpu", "authorized": n + 1}))
    full = store.read_events(dsn, limit=100)["events"]
    assert len(full) == 5
    collected, epoch, ordinal = [], 0, -1
    while True:
        page = store.read_events(dsn, cursor_epoch=epoch, cursor_ordinal=ordinal, limit=2)
        collected.extend(page["events"])
        epoch, ordinal = page["cursor_epoch"], page["cursor_ordinal"]
        if len(page["events"]) < 2:
            break
    assert [e["payload"] for e in collected] == [e["payload"] for e in full]


def test_cursor_misses_nothing_under_late_commit(migrated_db):
    dsn = migrated_db
    store.seed_allocation(dsn, _cmd({"allocation_id": "a0", "domain": "cpu", "authorized": 1}))
    cursor = store.read_events(dsn)
    assert len(cursor["events"]) == 1

    release, held = threading.Event(), threading.Event()

    def late_writer():
        with db.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                cur.execute("SELECT event_epoch FROM control WHERE id = 1 FOR UPDATE")
                epoch = cur.fetchone()[0] + 1
                held.set()
                assert release.wait(timeout=15)
                cur.execute("UPDATE control SET event_epoch = %s WHERE id = 1", (epoch,))
                cur.execute(
                    "INSERT INTO domain_events (epoch, ordinal, kind, payload) VALUES (%s, 0, %s, %s)",
                    (epoch, "test.late", '{"n": 1}'),
                )
                conn.commit()

    worker = threading.Thread(target=late_writer)
    worker.start()
    assert held.wait(timeout=15)
    during = store.read_events(dsn, cursor_epoch=cursor["cursor_epoch"],
                               cursor_ordinal=cursor["cursor_ordinal"])
    assert during["events"] == []
    release.set()
    worker.join(timeout=15)
    after = store.read_events(dsn, cursor_epoch=cursor["cursor_epoch"],
                              cursor_ordinal=cursor["cursor_ordinal"])
    assert [e["kind"] for e in after["events"]] == ["test.late"]
    full = store.read_events(dsn)["events"]
    epochs = [e["epoch"] for e in full]
    assert epochs == sorted(epochs) == [1, 2]
    assert store.get_control(dsn)["event_epoch"] == 2


def test_concurrent_transitions_keep_total_order(migrated_db):
    dsn = migrated_db
    errors: list = []

    def seed(n: int):
        try:
            result = store.seed_allocation(
                dsn, Command(request_id=f"conc-{n}", deadline_ms=30_000,
                             payload={"allocation_id": f"c{n}", "domain": "cpu", "authorized": 1}))
            assert result.code == ResultCode.APPLIED
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=seed, args=(n,)) for n in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert errors == []
    got = store.read_events(dsn, limit=100)["events"]
    assert [e["epoch"] for e in got] == [1, 2, 3, 4, 5, 6]
    time.sleep(0)
