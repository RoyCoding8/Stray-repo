from __future__ import annotations

import os
import threading
import uuid
from pathlib import Path

import pytest

from hypothesis import given, settings
from hypothesis import strategies as st
from psycopg.rows import dict_row

from settlement import db, store
from settlement.common import Command, ResultCode


def _cmd(payload: dict, **kw) -> Command:
    return Command(request_id=f"req_{uuid.uuid4().hex[:12]}", payload=payload, **kw)


def _balances(dsn, aid="a1"):
    with db.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT authorized, consumed, reserved FROM allocations WHERE id = %s", (aid,))
            row = cur.fetchone()
            conn.commit()
            return int(row["authorized"]), int(row["consumed"]), int(row["reserved"])


def test_concurrent_last_units_only_feasible_commit(migrated_db):
    dsn = migrated_db
    assert store.seed_allocation(dsn, _cmd({"allocation_id": "a1", "domain": "cpu", "authorized": 10})).code \
        == ResultCode.APPLIED
    outcomes: dict = {}

    def attempt(n: int):
        try:
            result = store.reserve(
                dsn, Command(request_id=f"race-{n}", deadline_ms=60_000,
                             payload={"allocation_id": "a1", "reservation_id": f"r{n}", "amount": 5}))
            outcomes[n] = result.code
        except Exception as exc:  # noqa: BLE001
            outcomes[n] = exc

    threads = [threading.Thread(target=attempt, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=90)
    assert len(outcomes) == 8
    applied = sum(1 for v in outcomes.values() if v == ResultCode.APPLIED)
    refused = sum(1 for v in outcomes.values() if v == ResultCode.INSUFFICIENT_RESOURCES)
    assert applied == 2
    assert refused == 6
    authorized, consumed, reserved = _balances(dsn)
    assert (authorized, consumed, reserved) == (10, 0, 10)


def test_budget_conservation_under_concurrency(migrated_db):
    dsn = migrated_db
    store.seed_allocation(dsn, _cmd({"allocation_id": "a1", "domain": "cpu", "authorized": 100}))

    def attempt(n: int):
        store.reserve(dsn, Command(request_id=f"mix-{n}", deadline_ms=60_000,
                                   payload={"allocation_id": "a1", "reservation_id": f"m{n}", "amount": 7}))

    threads = [threading.Thread(target=attempt, args=(n,)) for n in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=90)
    authorized, consumed, reserved = _balances(dsn)
    assert consumed + reserved <= authorized
    assert reserved == 14 * 7


def test_subdivide_partitions_parent_capacity(migrated_db):
    dsn = migrated_db
    store.seed_allocation(dsn, _cmd({"allocation_id": "root", "domain": "cpu", "authorized": 100}))
    ok = store.subdivide_allocation(dsn, _cmd({"parent_id": "root", "child_id": "c1", "authorized": 60}))
    assert ok.code == ResultCode.APPLIED
    too_big = store.subdivide_allocation(dsn, _cmd({"parent_id": "root", "child_id": "c2", "authorized": 50}))
    assert too_big.code == ResultCode.INSUFFICIENT_RESOURCES
    exact = store.subdivide_allocation(dsn, _cmd({"parent_id": "root", "child_id": "c2", "authorized": 40}))
    assert exact.code == ResultCode.APPLIED
    third = store.subdivide_allocation(dsn, _cmd({"parent_id": "root", "child_id": "c3", "authorized": 1}))
    assert third.code == ResultCode.INSUFFICIENT_RESOURCES


def test_settle_converts_once_and_uncertain_retains_exposure(migrated_db):
    dsn = migrated_db
    store.seed_allocation(dsn, _cmd({"allocation_id": "a1", "domain": "cpu", "authorized": 100}))
    store.reserve(dsn, _cmd({"allocation_id": "a1", "reservation_id": "r1", "amount": 30}))
    store.reserve(dsn, _cmd({"allocation_id": "a1", "reservation_id": "r2", "amount": 20}))
    assert store.settle_reservation(dsn, _cmd({"reservation_id": "r2", "outcome": "unknown"})).code \
        == ResultCode.ALREADY_APPLIED
    assert _balances(dsn) == (100, 0, 50)
    first = store.settle_reservation(dsn, _cmd({"reservation_id": "r1", "outcome": "success"}))
    assert first.code == ResultCode.APPLIED and first.data["settled"] is True
    assert _balances(dsn) == (100, 30, 20)
    again = store.settle_reservation(dsn, _cmd({"reservation_id": "r1", "outcome": "success"}))
    assert again.code == ResultCode.ALREADY_APPLIED
    assert _balances(dsn) == (100, 30, 20)
    late = store.settle_reservation(dsn, _cmd({"reservation_id": "r2", "outcome": "failure"}))
    assert late.data["settled"] is True
    assert _balances(dsn) == (100, 50, 0)


def test_release_returns_capacity_and_over_budget_refused(migrated_db):
    dsn = migrated_db
    store.seed_allocation(dsn, _cmd({"allocation_id": "a1", "domain": "cpu", "authorized": 10}))
    assert store.reserve(dsn, _cmd({"allocation_id": "a1", "reservation_id": "r1", "amount": 11})).code \
        == ResultCode.INSUFFICIENT_RESOURCES
    assert store.reserve(dsn, _cmd({"allocation_id": "a1", "reservation_id": "r1", "amount": 8})).code \
        == ResultCode.APPLIED
    assert store.release_reservation(dsn, _cmd({"reservation_id": "r1"})).code == ResultCode.APPLIED
    assert _balances(dsn) == (10, 0, 0)
    assert store.release_reservation(dsn, _cmd({"reservation_id": "r1"})).code == ResultCode.ALREADY_APPLIED


@given(st.lists(st.tuples(st.integers(1, 40), st.sampled_from(["success", "failure", "unknown", "release"])),
               min_size=1, max_size=25))
@settings(max_examples=40, deadline=None)
def test_random_reserve_settle_sequences_preserve_invariant(ops):
    dsn = os.environ.get("SETTLEMENT_TEST_DSN", "")
    if not dsn:
        pytest.skip("SETTLEMENT_TEST_DSN is not configured")
    db.apply_migrations(dsn, Path(__file__).parent.parent / "migrations")
    with db.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                " AND tablename != 'schema_migrations'")
            for row in cur.fetchall():
                cur.execute(f'TRUNCATE TABLE "{row[0]}" CASCADE')
        conn.commit()
    aid = f"h_{uuid.uuid4().hex[:8]}"
    store.seed_allocation(dsn, _cmd({"allocation_id": aid, "domain": "cpu", "authorized": 100}))
    for n, (amount, action) in enumerate(ops):
        rid = f"{aid}-r{n}"
        got = store.reserve(dsn, _cmd({"allocation_id": aid, "reservation_id": rid, "amount": amount}))
        if got.code == ResultCode.APPLIED:
            if action == "release":
                assert store.release_reservation(dsn, _cmd({"reservation_id": rid})).code == ResultCode.APPLIED
            else:
                settled = store.settle_reservation(dsn, _cmd({"reservation_id": rid, "outcome": action}))
                if action != "unknown":
                    assert settled.data["settled"] is True
        authorized, consumed, reserved = _balances(dsn, aid)
        assert consumed + reserved <= authorized
        assert consumed >= 0 and reserved >= 0
