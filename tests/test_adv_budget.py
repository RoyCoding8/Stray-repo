from __future__ import annotations

import threading
import uuid

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st
from hypothesis.stateful import (RuleBasedStateMachine, invariant, rule,
                                    run_state_machine_as_test)

from settlement import store
from settlement.common import Command, ConflictPayload, ResultCode


def _cmd(payload: dict, tag: str = "") -> Command:
    return Command(request_id=f"adv_{tag}_{uuid.uuid4().hex[:10]}", payload=payload)


def _env(dsn, tag, authorized=1000):
    store.seed_grant(dsn, _cmd({"version": 1, "charter_text": "adv",
                                "authority_grant": {}, "envelopes": {}}, f"{tag}g"))
    store.seed_allocation(dsn, _cmd({"allocation_id": f"{tag}-a", "domain": "cpu",
                                     "authorized": authorized}, f"{tag}a"))
    store.admit_commitment(dsn, _cmd({"investigation_id": f"{tag}-i",
                                      "objective": "adv"}, f"{tag}i"))
    return f"{tag}-a", f"{tag}-i"


def test_last_units_race(migrated_db):
    dsn = migrated_db
    alloc, _ = _env(dsn, "race", authorized=10)
    codes = []
    lock = threading.Lock()

    def worker(n):
        res = store.reserve(dsn, _cmd({"allocation_id": alloc,
                                       "reservation_id": f"race-r{n}",
                                       "amount": 5}, f"racer{n}"))
        with lock:
            codes.append(res.code)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert codes.count(ResultCode.APPLIED) == 2
    assert codes.count(ResultCode.INSUFFICIENT_RESOURCES) == 6
    status = store.allocation_status(dsn, alloc)
    assert (status["authorized"], status["reserved"], status["consumed"]) == (10, 10, 0)


def test_journal_replay_consistency(migrated_db):
    dsn = migrated_db
    alloc, _ = _env(dsn, "jrnl")
    payload = {"allocation_id": alloc, "reservation_id": "jrnl-r1", "amount": 7}
    first = store.reserve(dsn, Command(request_id="jrnl-fixed-1", payload=payload))
    assert first.code == ResultCode.APPLIED
    replay = store.reserve(dsn, Command(request_id="jrnl-fixed-1", payload=dict(payload)))
    assert replay.code == ResultCode.ALREADY_APPLIED
    assert replay.data == first.data
    with pytest.raises(ConflictPayload):
        store.reserve(dsn, Command(request_id="jrnl-fixed-1",
                                   payload={**payload, "amount": 8}))
    assert store.allocation_status(dsn, alloc)["reserved"] == 7


def test_outbox_exactly_once_delivery_effects(migrated_db):
    dsn = migrated_db
    alloc, inv = _env(dsn, "obx")
    store.acquire_work(dsn, _cmd({"attempt_id": "obx-att", "investigation_id": inv}, "obxq"))
    store.prepare_operation(dsn, _cmd(
        {"operation_id": "obx-op", "attempt_id": "obx-att", "allocation_id": alloc,
         "reservation_id": "res-obx-op", "exposure": 10,
         "operation": {"effect": "sandbox-exec", "payload": {}}}, "obxp"))
    assert store.scan_outbox(dsn) == []
    store.advance_dispatch(dsn, _cmd({"operation_id": "obx-op",
                                      "launcher_id": "fake-1"}, "obxa"))
    intents = store.scan_outbox(dsn)
    assert [i["workflow_identity"] for i in intents] == ["dispatch:obx-op"]
    claimed = store.claim_outbox(dsn, _cmd({"workflow_identity": "dispatch:obx-op"},
                                           "obxc"))
    assert claimed.code == ResultCode.APPLIED
    redeliver = store.claim_outbox(dsn, _cmd({"workflow_identity": "dispatch:obx-op"},
                                             "obxc2"))
    assert redeliver.data["delivered"] is False
    assert redeliver.data["payload"] == claimed.data["payload"]
    first = store.record_delivery(dsn, _cmd({"workflow_identity": "dispatch:obx-op"}, "obxd"))
    assert first.code == ResultCode.APPLIED
    second = store.record_delivery(dsn, _cmd({"workflow_identity": "dispatch:obx-op"}, "obxd2"))
    assert second.code == ResultCode.ALREADY_APPLIED
    assert store.scan_outbox(dsn) == []


def test_epoch_monotonicity_and_cursor(migrated_db):
    dsn = migrated_db
    alloc, inv = _env(dsn, "epo")
    store.acquire_work(dsn, _cmd({"attempt_id": "epo-att", "investigation_id": inv}, "epoq"))
    for n in range(5):
        store.reserve(dsn, _cmd({"allocation_id": alloc,
                                 "reservation_id": f"epo-r{n}", "amount": 1}, f"epo{n}"))
    full = store.read_events(dsn, limit=1000)["events"]
    keys = [(e["epoch"], e["ordinal"]) for e in full]
    assert keys == sorted(keys) and len(set(keys)) == len(keys)
    assert all(e >= 1 for e, _ in keys)
    page, cursor = [], (0, -1)
    while True:
        chunk = store.read_events(dsn, cursor_epoch=cursor[0],
                                  cursor_ordinal=cursor[1], limit=3)
        page.extend(chunk["events"])
        if len(chunk["events"]) < 3:
            break
        cursor = (chunk["cursor_epoch"], chunk["cursor_ordinal"])
    assert [(e["epoch"], e["ordinal"]) for e in page] == keys


def test_settle_once_and_no_duplicate_spend(migrated_db):
    dsn = migrated_db
    alloc, _ = _env(dsn, "stl", authorized=100)
    store.reserve(dsn, _cmd({"allocation_id": alloc, "reservation_id": "stl-r",
                             "amount": 40}, "stl1"))
    first = store.settle_reservation(dsn, _cmd({"reservation_id": "stl-r",
                                                "outcome": "success",
                                                "actual_cost": 25}, "stl2"))
    assert first.code == ResultCode.APPLIED and first.data["consumed"] == 25
    second = store.settle_reservation(dsn, _cmd({"reservation_id": "stl-r",
                                                 "outcome": "success"}, "stl3"))
    assert second.code == ResultCode.ALREADY_APPLIED
    status = store.allocation_status(dsn, alloc)
    assert (status["consumed"], status["reserved"]) == (25, 0)
    refused = store.release_reservation(dsn, _cmd({"reservation_id": "stl-r"}, "stl4"))
    assert refused.code == ResultCode.INVALID_INPUT
    assert "already settled" in refused.detail


def test_fulfill_once_per_revision(migrated_db):
    dsn = migrated_db
    alloc, inv = _env(dsn, "ful")
    gen = store.acquire_work(
        dsn, _cmd({"attempt_id": "ful-att", "investigation_id": inv}, "fulq")
    ).data["ownership_generation"]
    done = store.complete_attempt(
        dsn, _cmd({"attempt_id": "ful-att", "ownership_generation": gen,
                   "outcome": "completed"}, "ful0"))
    assert done.code == ResultCode.APPLIED
    control = store.get_control(dsn)
    full = {"investigation_id": inv, "attempt_id": "ful-att",
            "ownership_generation": gen, "revision": 1,
            "authority_version": int(control["authority_version"]),
            "evidence_epoch": int(control["evidence_epoch"]), "obligations": {}}
    first = store.fulfill_investigation(dsn, _cmd(dict(full), "ful1"))
    assert first.code == ResultCode.APPLIED
    second = store.fulfill_investigation(dsn, _cmd(dict(full), "ful2"))
    assert second.code != ResultCode.APPLIED
    assert "already fulfilled" in second.detail
    obs = store.submit_observation(dsn, _cmd({"attempt_id": "ful-att",
                                              "content": {"note": "late"}}, "ful3"))
    assert obs.code == ResultCode.APPLIED


class BudgetMachine(RuleBasedStateMachine):
    def __init__(self, dsn):
        super().__init__()
        self.dsn = dsn
        self.alloc = f"sm-a-{uuid.uuid4().hex[:6]}"
        store.seed_allocation(dsn, _cmd({"allocation_id": self.alloc, "domain": "cpu",
                                         "authorized": 200}, "smseed"))
        self.children: dict[str, int] = {}
        self.live: dict[str, tuple[str, int]] = {}

    @rule(child=st.text(min_size=1, max_size=6, alphabet="abc"),
          amount=st.integers(min_value=1, max_value=60))
    def subdivide(self, child, amount):
        cid = f"{self.alloc}-{child}"
        if cid in self.children:
            return
        res = store.subdivide_allocation(
            self.dsn, _cmd({"parent_id": self.alloc, "child_id": cid,
                            "domain": "cpu", "authorized": amount}, "smsub"))
        if res.code == ResultCode.APPLIED:
            self.children[cid] = amount

    @rule(idx=st.integers(min_value=0, max_value=7),
          amount=st.integers(min_value=1, max_value=50))
    def reserve(self, idx, amount):
        pool = [self.alloc, *sorted(self.children)]
        aid = pool[idx % len(pool)]
        rid = f"sm-r-{uuid.uuid4().hex[:8]}"
        res = store.reserve(self.dsn, _cmd({"allocation_id": aid, "reservation_id": rid,
                                            "amount": amount}, "smres"))
        if res.code == ResultCode.APPLIED:
            self.live[rid] = (aid, amount)

    @rule()
    def settle_one(self):
        if not self.live:
            return
        rid = sorted(self.live)[0]
        aid, amount = self.live.pop(rid)
        actual = amount // 2
        res = store.settle_reservation(
            self.dsn, _cmd({"reservation_id": rid, "outcome": "success",
                            "actual_cost": actual}, "smset"))
        assert res.code == ResultCode.APPLIED and res.data["consumed"] == actual

    @rule()
    def release_one(self):
        if not self.live:
            return
        rid = sorted(self.live)[-1]
        self.live.pop(rid)
        res = store.release_reservation(self.dsn, _cmd({"reservation_id": rid}, "smrel"))
        assert res.code == ResultCode.APPLIED

    @invariant()
    def conservation(self):
        for aid in [self.alloc, *self.children]:
            status = store.allocation_status(self.dsn, aid)
            assert status["consumed"] + status["reserved"] <= status["authorized"]
        parent = store.allocation_status(self.dsn, self.alloc)
        assert sum(self.children.values()) + parent["consumed"] + parent["reserved"] \
            <= parent["authorized"]


@pytest.fixture()
def _machine_dsn(migrated_db):
    return migrated_db


def test_budget_state_machine(_machine_dsn):
    dsn = _machine_dsn

    class Bound(BudgetMachine):
        def __init__(self):
            super().__init__(dsn)

    run_state_machine_as_test(
        Bound, settings=settings(max_examples=12, deadline=None,
                                 suppress_health_check=list(HealthCheck)))
